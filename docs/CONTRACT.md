# CONTRACT.md — Kaizen Test & Execution Contract

## 0. Purpose

This document defines the **canonical contract** between:

- **QA / Portal** — how tests are authored and viewed
- **Planner / LLM** — how English steps are turned into tool calls
- **Engine** — how plans are executed
- **PageBrain** — how elements are resolved and learned over time
- **Eval / Datasets** — how we log and export data for training

The goal is to:

- Lock in a **stable mental model** for tests and runs.
- Make it possible to evolve the Engine, Planner, and PageBrain **without constantly changing the API**.
- Ensure **everything** (UI, planner, engine, PageBrain, datasets) agrees on what a **test**, a **step**, and a **run** mean.

We use:

- **Step-based English tests** (Option 1)
- **Hybrid per-step planning with full-test context** (Mode C)

---

## 1. Test Authoring Model (Portal ↔ Engine)

### 1.1 Test

A **Test** is the core unit that a QA creates and maintains.

```jsonc
{
  "id": "test_123",
  "name": "Login and see dashboard",
  "description": "Basic happy-path login flow to reach the dashboard.",
  "app_base_url": "https://app.example.com",
  "tags": ["smoke", "login"],
  "steps": [
    {
      "id": "step_1",
      "index": 1,
      "text": "Open the login page.",
      "expected": "The login form is visible."
    },
    {
      "id": "step_2",
      "index": 2,
      "text": "Fill in my email and password and submit the form.",
      "expected": "I am logged in."
    },
    {
      "id": "step_3",
      "index": 3,
      "text": "Verify that the dashboard is displayed.",
      "expected": "The URL contains /dashboard and the welcome message is visible."
    }
  ]
}
```

**Fields:**

- `id`: Stable unique test identifier.
- `name`: Short human-friendly name.
- `description`: Optional long description / scenario.
- `app_base_url`: Base URL / app under test.
- `tags`: Optional labels (e.g. `smoke`, `regression`, `login`).
- `steps`: Ordered list of **Steps**.

### 1.2 Step

Each **Step** is a single English instruction plus optional expected outcome.

```jsonc
{
  "id": "step_2",
  "index": 2,
  "text": "Fill in my email and password and submit the form.",
  "expected": "I am logged in."
}
```

**Fields:**

- `id`: Stable per-test step ID (used in runs, logs, datasets).
- `index`: 1-based order within the test.
- `text`: English instruction (what QA writes).
- `expected`: Optional description of what success looks like in QA terms.

> UX note: later, a block-based UI can generate these same steps under the hood.

---

## 2. Planner Contract (Hybrid Mode C)

We use **Hybrid per-step planning with full-test context**:

- For each step, the planner receives:
  - Full list of steps (for context).
  - The index of the current step.
  - The current step text and expected outcome.
- Planner returns **only the tool calls for this step**.

### 2.1 Planner Request

For a given test + step:

```jsonc
{
  "test_id": "test_123",
  "run_id": "run_456",

  "test_title": "Login and see dashboard",
  "app_base_url": "https://app.example.com",

  "all_steps": [
    "Open the login page.",
    "Fill in my email and password and submit the form.",
    "Verify that the dashboard is displayed."
  ],

  "current_step_index": 2,
  "current_step": {
    "id": "step_2",
    "index": 2,
    "text": "Fill in my email and password and submit the form.",
    "expected": "I am logged in."
  }
}
```

> Planner is free to use `all_steps` for context but must only produce actions for `current_step`.

### 2.2 Planner Response

Planner returns a **plan for this step only** as a list of tool calls.

```jsonc
{
  "step_id": "step_2",
  "path": "llm", // or "glue", "mixed", etc.
  "tool_calls": [
    {
      "tool": "waitFor",
      "args": {
        "condition": "visible",
        "target": "email input"
      }
    },
    {
      "tool": "type",
      "args": {
        "target": "email input",
        "text": "qa@example.com"
      }
    },
    {
      "tool": "type",
      "args": {
        "target": "password input",
        "text": "SuperSecret123"
      }
    },
    {
      "tool": "press",
      "args": {
        "target": "password input",
        "key": "Enter"
      }
    }
  ]
}
```

**Fields:**

- `step_id`: Must match the input step.
- `path`: Which planner path was used (`llm`, `glue`, `llm+glue`, etc.).
- `tool_calls`: Ordered list of tool calls (click/type/waitFor/assert/etc.) using **semantic targets** (e.g. `"email input"`, `"login button"`) that PageBrain will resolve.

---

## 3. Execution Contract (Engine ↔ PageBrain ↔ Healer)

### 3.1 Action Lifecycle

For each `tool_call` in a step plan:

1. Engine receives `{ tool, args.semantic target }`.
2. PageBrain is called to resolve the **concrete element** (selector / handle) for that semantic target.
3. Engine executes the action on that element.
4. If it fails, the **Healer** may be invoked to recover.
5. Artifacts are captured (screenshots, DOM snapshots).
6. Results are logged into the run structure.

### 3.2 PageBrain Request

```jsonc
{
  "tenant_id": "tenant_1",
  "run_id": "run_456",
  "step_id": "step_2",
  "action_index": 2,

  "instruction": "Fill in my email and password and submit the form.",
  "semantic_target": "login button",

  "dom_snapshot_id": "dom_snap_790",
  "candidate_elements": [
    {
      "element_id": "el_201"
      // PageBrain internally knows or can derive features for this
    },
    {
      "element_id": "el_202"
    }
  ],

  "context": {
    "app_base_url": "https://app.example.com",
    "registrable_domain": "example.com",
    "profiles_enabled": true,
    "retrieval_enabled": true
  }
}
```

### 3.3 PageBrain Response

```jsonc
{
  "source": "pagebrain_v1",
  "chosen_element_id": "el_201",
  "confidence": 0.82,
  "scored_candidates": [
    { "element_id": "el_201", "score": 0.82 },
    { "element_id": "el_202", "score": 0.65 }
  ]
}
```

Engine then translates `element_id` into the actual selector / handle used for execution.

---

## 4. Run Result Schema (Engine ↔ Portal ↔ Datasets)

### 4.1 Run

```jsonc
{
  "run_id": "run_456",
  "test_id": "test_123",
  "tenant_id": "tenant_1",

  "status": "passed", // "failed", "error", "cancelled"
  "app_base_url": "https://app.example.com",

  "started_at": "2025-11-20T10:00:00Z",
  "finished_at": "2025-11-20T10:01:23Z",

  "environment": {
    "browser": "chromium",
    "viewport": { "width": 1280, "height": 720 }
  },

  "steps": [ /* StepRun[] */ ]
}
```

### 4.2 StepRun

```jsonc
{
  "step_run_id": "step_run_2",
  "step_id": "step_2",
  "index": 2,

  "author_text": "Fill in my email and password and submit the form.",
  "expected": "I am logged in.",

  "status": "passed", // "failed", "skipped", "error"
  "started_at": "2025-11-20T10:00:20Z",
  "finished_at": "2025-11-20T10:00:45Z",

  "planner": {
    "path": "llm",
    "tool_calls": [
      {
        "tool": "type",
        "args": { "target": "email input", "text": "qa@example.com" }
      },
      {
        "tool": "type",
        "args": { "target": "password input", "text": "SuperSecret123" }
      },
      {
        "tool": "press",
        "args": { "target": "password input", "key": "Enter" }
      }
    ]
  },

  "actions": [ /* ActionRun[] */ ],

  "final_assertions": [
    {
      "type": "url_contains",
      "value": "/dashboard",
      "status": "passed"
    }
  ],

  "artifacts": {
    "summary_screenshot": "s3://.../run_456/step_2_summary.png",
    "logs_path": "s3://.../run_456/step_2_logs.jsonl"
  }
}
```

### 4.3 ActionRun

```jsonc
{
  "action_index": 2,
  "tool": "click",
  "semantic_target": "login button",

  "pagebrain": {
    "source": "pagebrain_v1",
    "chosen_element_id": "el_202",
    "confidence": 0.59,
    "scored_candidates": [
      { "element_id": "el_201", "score": 0.60 },
      { "element_id": "el_202", "score": 0.59 }
    ]
  },

  "executor": {
    "status": "failed", // "passed"
    "error": "element_not_interactable"
  },

  "healer": {
    "invoked": true,
    "chosen_element_id": "el_201",
    "reason": "profile + retrieval lift",
    "status": "passed"
  },

  "artifacts": {
    "screenshot_before": "s3://.../run_456/step_2_action_2_before.png",
    "screenshot_after": "s3://.../run_456/step_2_action_2_after_heal.png",
    "dom_snapshot_id": "dom_snap_790"
  }
}
```

**UI usage:**

- Show step list with `status`, `author_text`, `summary_screenshot`.
- Drill into a step shows:
  - planner path
  - human-readable element choice (derived from `element_id`)
  - artifacts.

**Engine / ML usage:**

- Use `planner`, `actions`, `pagebrain`, `healer` to build datasets and eval reports.

---

## 5. PageBrain Dataset Contract

PageBrain training examples are derived from **ActionRun** + success signals.

We only train on actions where:

- Final outcome is clearly successful:
  - Step passed and:
    - a post-condition assertion passed (e.g. `assertText`, `assertUrl`, element visible), **or**
    - strong success heuristic (e.g., known success page state).
- We can identify the **final correct element**:
  - If Healer was not invoked and executor passed: correct element = `pagebrain.chosen_element_id`.
  - If Healer fixed the action: correct element = `healer.chosen_element_id`.

### 5.1 Training Example Schema

```jsonc
{
  "example_id": "pb_000123",
  "tenant_id": "tenant_1",

  "test_id": "test_123",
  "run_id": "run_456",
  "step_id": "step_2",
  "action_index": 2,

  "instruction": "Fill in my email and password and submit the form.",
  "semantic_target": "login button",

  "dom_snapshot_id": "dom_snap_790",

  "candidates": [
    {
      "element_id": "el_201",
      "features": {
        "tag": "button",
        "text": "Log in",
        "role": "button",
        "depth": 12,
        "has_aria_label": true,
        "retrieval_score": 0.91,
        "profile_hit_score": 0.80,
        "same_domain_profile_hits": 3
      }
    },
    {
      "element_id": "el_202",
      "features": {
        "tag": "a",
        "text": "Log in",
        "role": "link",
        "depth": 5,
        "has_aria_label": false,
        "retrieval_score": 0.72,
        "profile_hit_score": 0.30,
        "same_domain_profile_hits": 0
      }
    }
  ],

  "pagebrain_choice": "el_202",
  "healer_choice": "el_201",
  "final_correct_element_id": "el_201",

  "label_source": "healer_success", // or "pagebrain_success", "fixture_truth"

  "created_at": "2025-11-20T10:05:00Z"
}
```

This supports:

- **Heuristic-only PageBrain** (ignore model, still log examples).
- **GBM ranker** (LightGBM / XGBoost) using `features` + labeled correct `final_correct_element_id`.
- Per-tenant models (respect `tenant_id`).

---

## 6. Versioning & Backwards Compatibility

- This contract is **v1** of the test/run/PageBrain semantics.
- Breaking changes (e.g., renaming fields, changing meaning) must be versioned:
  - `contract_version`: `"v1"` / `"v2"` at run and dataset level.
- Non-breaking additions (new optional fields) are allowed as long as:
  - existing code paths remain valid,
  - Portal can ignore unknown fields gracefully.

---

## 7. Summary (Mental Model)

- **Test** = QA-authored scenario, step-based English.
- **Step** = single QA intention with optional expected outcome.
- **Planner** = maps step → tool calls, using full test as context.
- **PageBrain** = maps semantic targets → concrete elements, per action.
- **Healer** = last-resort correction under drift.
- **Run** = structured record of test execution, step-by-step.
- **PageBrain Dataset** = extracted from successful actions with strong success signals.

This contract is the **source of truth** for how Kaizen behaves from QA’s first test to PageBrain’s learning loop.

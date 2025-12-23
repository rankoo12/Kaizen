# PageBrain Finder v2 - ARQ-Driven Design & Plan

## Goal

Build a new **PageBrain Finder** that, given a step target and a live page:

- Actively finds the intended element itself, not just re-rank an existing resolver list.
- Fuses all signals: DOM, text, existing resolver output, profiles/DB, retrieval, perception (screenshots/diffs), and user feedback.
- Uses a large multi-modal LLM as a **ranker**, under a strict, auditable protocol.
- Always returns:
  - A primary selector (top-1).
  - A ranked candidate list with metadata and rationale.
- Learns over time from pass/fail outcomes and explicit user feedback.

The existing non-LLM PageBrain ranker (GBM/tabular) remains a fallback and teacher. The long-term direction is that the LLM-backed Finder becomes primary, with the fallback acting as a safety net and distillation target.

---

## Core Design Principle

The LLM ranker is **not** a black box.

All LLM-based decisions in Finder v2 must:

- Follow **Attentive Reasoning Queries (ARQs)** – a structured, domain-specific reasoning blueprint.
- Re-state constraints just-in-time (visibility, enabled state, uniqueness, tool intent).
- Produce JSON-only output validated against a schema.
- Include verification fields that detect hallucination, guessing, or rule violations.
- Fail fast and fall back deterministically on schema violation, timeout, or self-declared uncertainty.

This aligns Finder v2 with Kaizen's core values: determinism, safety, debuggability, and observability.

---

## Scope (Finder v2)

### In scope

- `PageBrainFinder` implementation in `engine/core/pagebrain` that:
  - Owns candidate generation + ranking for live runs.
  - Uses the existing resolver as one signal source, not the sole authority.
  - Pulls historical hints from storage (profiles, retrieval, annotations).
  - Can invoke an LLM-based ranker operating under an ARQ protocol.
- Orchestrator integration:
  - `DeterministicPlanExecutor` delegates element choice to the Finder when enabled.
  - Action logs include a `pagebrain_finder` block with:
    - `candidates`
    - `ranking`
    - `chosen_index`
    - `engine` used (`llm_ranker` vs `fallback_ranker` vs `debug_marker`)
    - `model_id` (LLM model name or GBM model id)
- Dataset & training pipeline:
  - Export online runs into JSONL datasets.
  - Train a GBM/tabular fallback model.
  - Support periodic retraining from user feedback and outcomes.
  - Optionally distill the LLM's preferences into the GBM model.
- Portal integration:
  - Per-action view of Finder proposals.
  - Show which engine made the decision.
  - Allow users to mark predictions as correct/incorrect or select the right element.
  - Aggregate metrics to verify LLM lift over fallback.

### Out of scope

- Removing deterministic resolver or healer (they remain available).
- Cross-tenant/global training (respect existing isolation and privacy rules).

---

## Interfaces

### Finder API (engine)

```python
PageBrainFinder.find(target: dict) -> list[dict]
```

- Returns a list where index `0` is the chosen candidate (executor still expects 0 or 1 element).
- Maintains a `last_decision` object for logging and datasets:

```jsonc
{
  "path": "pagebrain_finder_v2",
  "engine": "llm_ranker | fallback_ranker | debug_marker",
  "llm_decision": "used | discarded_needs_more_data | discarded_violated | skipped_feedback | used_with_guess",
  "candidate_count": 5,
  "candidates": [
    {
      "rank": 0,
      "selector": { "type": "css", "value": "input[name=\"q\"]" },
      "visible": true,
      "enabled": true,
      "source": "dom"
    }
  ],
  "chosen_index": 0,
  "model_id": "<llm_model | gbm_model>",
  "reason": "short summary (e.g. llm_ranker)"
}
```

---

## Settings & Dependency Injection

### Finder selection

```text
PAGEBRAIN_FINDER_PATH = resolver | finder_v2
KAIZEN_PAGEBRAIN_FINDER_PATH
```

- `resolver`: current behavior (PageBrainResolver v1).
- `finder_v2`: use the new PageBrainFinder.

### Ranker mode

```text
PAGEBRAIN_RANKER_MODE = fallback | llm
KAIZEN_PAGEBRAIN_RANKER_MODE
```

- `fallback`: only GBM/tabular ranker.
- `llm`: attempt LLM ARQ ranker first; fall back on error/timeout/invalid JSON/uncertainty.

### LLM model selection

```text
PAGEBRAIN_LLM_MODEL = <provider/model-id>
KAIZEN_PAGEBRAIN_LLM_MODEL
```

Used by the `ILlmPageBrainRanker` implementation to know which multi-modal model to call.

### Container wiring

- Build `PageBrainModelStore` (fallback model).
- Build `PageBrainFinder` when enabled, injecting:
  - `model_store`
  - optional `llm_ranker: ILlmPageBrainRanker`

The plan is to keep executor wiring unchanged and enable v2 purely via configuration.

---

## Candidate Generation (Finder-owned, recall-first)

For a given `target` and live page, PageBrainFinder builds the candidate set. **The LLM never invents selectors**; it only ranks this set.

1. **Direct hints**
   - Use `target.css`, `target.id`, `target.testid` (when present) as strong hints and seed candidates.

2. **DOM scan (recall-first)**
   - Run a JS snippet to collect all **visible, enabled interactive elements** on the page:
     - `input`, `select`, `textarea`, `button`, `a`, `[role="button"]`, `[role="link"]`, and other clickable widgets if needed.
   - Attributes captured for each element:
     - tag, id, name, testid
     - aria-label, placeholder, text
     - visibility, enabled, bounding box
   - Filtering rules are **recall-first**:
     - Only drop elements that are clearly impossible for any action (e.g. permanently hidden or disabled).
     - Do **not** filter aggressively on semantics (e.g. matching target text) in a way that could exclude the true element.
   - From this large pool we may cap the number of **LLM-facing candidates** at a configurable `N_max` (for context size), but `N_max` is chosen so that the intended element is almost always present (for example, 50–200 candidates rather than 5–10).

3. **Profiles / DB hints**
   - From storage:
     - `locator_profiles`
     - `retrieval_embeddings`
   - Domain + tool + target-signature similarity.
   - Validate selectors exist and are visible before adding.

4. **Healer history**
   - Previously healed selectors for similar failures in this domain.

All candidates are normalized into:

```jsonc
{
  "selector": { "type": "css", "value": "..." },
  "visible": true,
  "enabled": true,
  "source": "dom | profile | retrieval | heuristic",
  "tag": "input",
  "id": "email",
  "aria_label": "Email",
  "text": "Email",
  "feedback": { "passed": 3, "failed": 1, "total": 4 }
}
```

---

## Ranking & Choice

The Finder supports two ranking paths.

### 1) LLM-based Ranker (Primary, ARQ-driven)

#### Role

The LLM does not generate selectors. It only ranks the provided candidates under strict constraints.

#### Inputs

- Step text + tool (e.g., `type "hello" into the search box`, `tool="type"`).
- Normalized candidates (up to `N_max`).
- Compact DOM neighborhood per candidate (serialized snippet).
- Optional perception data (bbox, diff metrics, screenshot crops).

#### ARQ-based Output Schema (conceptual)

The LLM must return JSON only, answering the following structured queries:

```jsonc
{
  "restate_task": { "tool": "click", "intent": "activate login button" },

  "hard_constraints": {
    "must_be_visible": true,
    "must_be_enabled": true,
    "must_be_unique": true
  },

  "candidate_elimination": [{ "index": 3, "reason": "not visible" }],

  "ranking": [0, 2, 1, 4],
  "scores": { "0": 0.92, "2": 0.71 },

  "top1_justification": {
    "matched_text": true,
    "matched_role": true,
    "source_preference": "profile"
  },

  "verification": {
    "violated_constraints": false,
    "guessed_fields": false
  },

  "needs_more_data": false
}
```

#### Finder behavior

- Validate schema; on any failure treat as LLM failure and use fallback ranker.
- Reject the LLM result if:
  - JSON is invalid.
  - `verification.violated_constraints = true`.
  - `verification.guessed_fields = true`.
  - `needs_more_data = true`.
- When accepted:
  - Reorder candidates according to `ranking`.
  - Log `engine = "llm_ranker"` and `model_id = PAGEBRAIN_LLM_MODEL`.

### 2) Fallback Ranker (GBM / tabular)

Used when:

- `PAGEBRAIN_RANKER_MODE = "fallback"`, or
- The LLM call fails / times out / returns invalid or unsafe output.

Behavior:

- Convert each candidate into numeric features (`FEATURE_KEYS`).
- Score candidates with a GBM model from `PageBrainModelStore`.
- Sort by score; pick top as primary.
- Log `engine = "fallback_ranker"` and `model_id = <gbm_model_id>`.

---

## Logging, Datasets & Observability

Each action run includes a `pagebrain_finder` block:

```jsonc
{
  "path": "pagebrain_finder_v2",
  "engine": "llm_ranker",
  "candidate_count": 7,
  "chosen_index": 0,
  "model_id": "pagebrain-llm-v1",
  "candidates": [...]
}
```

### Training dataset (JSONL)

One line per action:

```jsonc
{
  "run_id": "...",
  "action_index": 3,
  "tool": "click",
  "step_text": "Click Login",
  "candidates": [...],
  "label": 0,
  "label_source": "auto | user | healed | llm",
  "outcome": "passed",
  "engine": "llm_ranker | fallback_ranker"
}
```

ARQ verification fields allow us to down-weight lucky passes and flag unsafe decisions during training.

---

## Portal UX & Feedback Loop

### Per-action view

- Step text + tool.
- Final status.
- Selector actually used.
- PageBrain Finder panel:
  - Primary candidate.
  - Top-N list.
  - Engine badge (LLM vs fallback).

### Feedback controls

- "Finder prediction correct / wrong".
- Optional: select correct candidate.

Stored in `run_action_annotations` and fed back into training / evaluation.

---

## Phased Implementation Plan

### P0 - Skeleton & wiring

- Add finder path + ranker mode + LLM model settings.
- Implement `PageBrainFinder` shell.
- Candidate collection (direct hints + DOM + DB) + `last_decision` logging.

### P1 - Fallback model & datasets

- Dataset builder for Finder v2.
- GBM training/eval.
- Baseline metrics vs heuristic-only ranking.

### P2 - LLM ARQ ranker

- Define ARQ JSON schema.
- Implement `ILlmPageBrainRanker` (for example, `engine/core/pagebrain/llm_ranker.py`).
- Strict validation + GBM fallback.

### P3 - Portal UX & feedback

- Render Finder decisions in Run Details.
- Capture user annotations via feedback controls.

### P4 - Learning loop & rollout

- Retraining pipeline for fallback model (including LLM distillation).
- Shadow modes (LLM vs fallback).
- Gradual enablement via config per tenant/environment.

---

## Non-Negotiables

- No guessing: the LLM may only reason over provided candidates.
- Schema validation everywhere: reject any output that does not match ARQ schema or violates constraints.
- Fallback must always exist: GBM path can always make a choice.
- Every decision must be explainable after the fact via logged ARQ fields and rankings.

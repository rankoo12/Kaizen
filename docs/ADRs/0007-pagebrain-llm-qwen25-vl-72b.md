# 0007: Qwen2.5-VL-72B as PageBrain Finder LLM

Status: Accepted

## Context

- PageBrain Finder v2 is the new element-finding brain in Kaizen. It:
  - Enumerates candidate elements from the live DOM (recall-first).
  - Uses DB hints (locator profiles, retrieval embeddings) and healer history.
  - Applies human feedback (Passed/Failed) and a GBM/tabular fallback ranker.
  - Optionally calls an LLM ranker under an ARQ (Attentive Reasoning Queries) protocol to order candidates.
- We want the LLM ranker to:
  - Reason over **structured candidates + DOM context + perception** (screenshots/diffs).
  - Produce **strict JSON** following an ARQ schema (no free-form chatter).
  - Respect Kaizen’s principles:
    - Local-first.
    - No outbound network calls by default.
    - Deterministic, inspectable behavior.
    - Tenant privacy guarantees.
- We also want a model that is strong at:
  - Constraint satisfaction (must be visible, enabled, unique).
  - Ranking under rules instead of open-ended chat.
  - Grounded reasoning over DOM-like text and vision.

## Decision

We will standardize on **Qwen2.5-VL-72B-Instruct** as the primary LLM for PageBrain Finder v2, deployed as a **self-hosted, local service**.

- The model will be exposed via a local HTTP endpoint (e.g. `http://pagebrain-llm:9000/v1/chat/completions`) and wrapped by an `ILlmPageBrainRanker` implementation.
- Engine settings will select it via:
  - `PAGEBRAIN_LLM_MODEL` / `KAIZEN_PAGEBRAIN_LLM_MODEL` (e.g. `qwen2.5-vl-72b-instruct`).
  - `PAGEBRAIN_RANKER_MODE=llm` / `KAIZEN_PAGEBRAIN_RANKER_MODE=llm` to enable the LLM path.
- The ranker will:
  - Consume a compact representation of candidates (selector, attributes, source, feedback).
  - Optionally receive screenshot crops and perception metrics per candidate.
  - Answer an ARQ-style prompt with **JSON-only** payload containing:
    - `ranking` (indices best -> worst),
    - `scores` (per-candidate scores),
    - `verification` flags (constraint violations, guessed fields),
    - optional justifications.
  - Never invent new selectors; it may only rank the candidate list provided by PageBrainFinder.
- If Qwen output fails validation (JSON parse error, schema violation, `needs_more_data = true`, or constraint flags), PageBrainFinder:
  - Treats the LLM call as failed.
  - Falls back to the GBM/tabular ranker from `PageBrainModelStore`.

## Rationale

1. **Matches PageBrain’s workload**

PageBrain Finder is not a general chat agent. It is a constrained decision system:

- It receives a **finite set of candidates** with structured attributes.
- It must respect hard constraints (visible, enabled, unique).
- It must output a ranking in a machine-validated format.

Qwen2.5-VL-72B-Instruct is well-suited for:

- Structured reasoning and ranking over JSON-like inputs.
- Combining text signals (DOM attributes, labels, step text) with vision signals (element crops, diff scores).
- Obeying “do not guess / only use provided context” when given an explicit schema and ARQ guardrails.

2. **Vision is first-class**

Per the PageBrain Finder design, we want to incorporate:

- Screenshot crops around each candidate.
- Perception diff ratios and bounding boxes.
- Visual confirmation that the element “looks like” what the step describes.

Qwen2.5-VL-72B is a multi-modal model (VL) with strong performance on image+text tasks, making it a good fit for:

- Understanding UI layouts.
- Disambiguating visually similar elements.
- Cross-checking DOM attributes against what the user would see on screen.

3. **Local-first, privacy-preserving deployment**

- Qwen2.5-VL-72B can be run **entirely on our own hardware** (e.g., via vLLM/TensorRT-LLM).
- The Engine will talk only to a **local LLM service**:
  - No outbound network calls from Engine to external APIs.
  - Tenant data (DOM, screenshots, feedback) never leaves our infra.
- We can:
  - Control logging and retention at the LLM service layer.
  - Enforce per-tenant or per-environment isolation policies.

4. **ARQ + fallback mitigate open-model weaknesses**

Open models are still weaker than frontier hosted models for raw reasoning. However:

- ARQs constrain the model to:
  - Restate tasks and constraints.
  - Explicitly eliminate candidates that violate constraints.
  - Declare when it is unsure or needs more data.
- Schema validation lets us **reject unsafe / malformed** outputs.
- The GBM/tabular ranker provides a **deterministic fallback**:
  - If Qwen fails, times out, or self-reports uncertainty, we still have a decision path.

This pattern aligns with our existing safety expectations and makes it possible to use a large local model without turning the system into a black-box.

## Consequences

### Positive

- Stronger, more “human-like” element selection:
  - Better at understanding step intent (e.g., “search box” vs “search by voice” icon).
  - Better at resolving ambiguous or visually-driven targets.
- Local, privacy-preserving inference:
  - No dependence on external vendors for live PageBrain decisions.
  - Easier to reason about data residency and compliance.
- Clear separation of concerns:
  - PageBrainFinder owns candidate generation and safety rails.
  - Qwen2.5-VL-72B acts as a pluggable ranker behind `ILlmPageBrainRanker`.
  - GBM/tabular ranker remains as a deterministic backup.

### Negative / Risks

- **Hardware cost and latency**:
  - 72B VL is large; it requires significant GPU resources.
  - Per-action latency will be higher than a small model, especially when passing many candidates.
  - Mitigation: we will tune `N_max` (LLM-facing candidate count) and allow a smaller Qwen-VL variant later if needed.
- **Operational complexity**:
  - We must run and monitor a local LLM service, including:
    - model download and versioning,
    - GPU scheduling,
    - health checks,
    - observability and logging.
- **Model quality drift**:
  - Future Qwen releases may behave differently.
  - Mitigation: pin to a specific version tag (e.g. `qwen2.5-vl-72b-instruct`) and treat upgrades as explicit ADRs with evaluation runs.

### Follow-up work

- Implement `ILlmPageBrainRanker` and a `QwenLlmPageBrainRanker` that:
  - Builds ARQ prompts from PageBrainFinder inputs.
  - Calls the local Qwen2.5-VL-72B endpoint with deterministic decoding parameters.
  - Enforces JSON schema validation and converts responses to a ranked candidate list.
- Wire LLM ranker into `PageBrainFinder.find(...)` behind:
  - `PAGEBRAIN_RANKER_MODE=llm`
  - With GBM fallback on any failure or self-reported uncertainty.
- Add evaluation scripts to:
  - Compare Qwen vs GBM vs heuristic-only performance on recorded datasets.
  - Support distillation of Qwen preferences back into the GBM tabular model.

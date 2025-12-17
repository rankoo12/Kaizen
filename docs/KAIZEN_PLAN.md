# Kaizen - End Goal, Status, and Strict Plan

Legend: [X] Done [~] Planned/In Progress [ ] Not Started (\*) Vision/Goal

---

## End Goal (\*)

- QA writes plain English tests and runs them locally and in the cloud (SaaS).
- Tests are authored as **step-based English scenarios** (see `CONTRACT.md`), with a stable mapping from QA steps → planner steps → engine actions.
- The Engine plans and executes via Playwright first (adapters allow Selenium/WebDriver BiDi later), resolves elements robustly, and heals selectors.
- The Portal is a multi-tenant app for authoring tests, launching runs, reviewing artifacts and metrics, managing models, and connecting repos.
- Kaizen "learns" over time: cross-site retrieval uses embeddings, profiles, heuristics, PageBrain ranking, and (optional) vision to approach near-100% element finding, with strong privacy and tenant isolation.
- Planner/LLM knows **what** to do in QA terms; PageBrain knows **where** to do it on the page; Healer recovers from the remaining failures and feeds back into learning.

---

## Current Status Snapshot

- Engine ([X]): FastAPI API/CLI; orchestrator + deterministic plan executor; DOM resolver v1; handlers for open/click/type/press.
- Engine extensions ([X]): Added handlers for wait/assert/custom; wiring and tests included in this change.
- Storage ([X]): In-memory + Postgres backend; settings + DI; basic profiles persisted.
- Portal ([~]): Thin backend with minimal HTML page; NL run; runs polling; artifacts view basics.
- Infra/CI ([X]): Docker Compose; Jenkins pipeline via `scripts/ci.sh`; OTel + Prometheus/Grafana/Jaeger.
- Security ([X]): Safe URL allow-list, schema validation, local LLM via Ollama; structured logs; no secrets in repo.
- Learning & Retrieval ([X]): Locator profiles with drift handling; pgvector-ready embeddings; retrieval mixed into healer; planner QA corpus and eval harness in place (planner side).
- Authoring & Run Contract ([~]): Step-based English test model and hybrid per-step planning contract defined in `CONTRACT.md`; not yet fully wired into all APIs and Portal flows.

---

## What Is Missing or To Add

- Action Coverage ([~]): `waitFor`/`assertVisible`/`assertText`/`assertUrl`/`custom` are implemented with unit tests; future polish as needed.
- Migrations/Indexes ([~]): Alembic plus indexes per ADR-0006; durable queue on Postgres.
- Portal UX ([~]): Runs list, details, artifact previews; later a proper React/Next.js UI.
- AuthN/Z and Tenancy ([ ]): API keys or JWT, tenants/users, RBAC, per-tenant isolation.
- Artifact Storage ([~]): FS default; optional S3/MinIO; retention policy.
- PageBrain Element Ranking ([X]): First-class PageBrain module between planner and executor; heuristic + retrieval ranking with clean API.
- PageBrain Logging & Dataset ([X]): Per-step logging of instruction, DOM slice, candidates, chosen selector, healer corrections and success signals; export/curation scripts for PageBrain training (aligned with `CONTRACT.md`).
- PageBrain ML Ranker ([X]): Training pipeline (GBM-style ranker) over PageBrain features; offline eval harness; per-tenant model artifacts.
- Perception & Visual Validation ([ ]): PerceptionLayer abstraction combining DOM + screenshots (+ optional vision) with 3-layer visual diff (element / main-content / full page), outcome assessment per step, and a feedback loop feeding PageBrain.
- Contract Wiring ([ ]): Full implementation of `CONTRACT.md` for test definition, planner requests, run results, and PageBrain dataset exports.
- Multi-browser ([ ]): Selenium/WebDriver BiDi adapter via `IBrowser`.
- Scheduler ([ ]): Suite CRUD plus periodic runs.
- Cloud ([ ]): Helm/Kubernetes, HPA for runners; Terraform for dev env.
- Compliance ([ ]): Audit logs, backups, data retention, billing/quotas.

---

## Strict, Test-First Plan

### P0 - Reliability First

1. Implement missing handlers (wait/assert/custom) - STATUS: [X]
   - **DoD:** `waitFor`/`assertVisible`/`assertText`/`assertUrl`/`custom` handlers wired in DI and executor target resolution; README examples added later.
   - **Tests:** Unit per handler; simple integration via executor can follow.

1b) Core actions completeness (desktop web only) - STATUS: [X]

- **DoD:** `click`/`double-click`/`context-click`/`hover`/`focus`/`blur`/`type`/`clear`/`select` (dropdown)/`upload` file/drag and drop; scroll to/up/down/left/right; reload/back/forward; open/close/switch tab or window.
- **Delivered:** all action primitives plus navigation (reload/back/forward/new tab/window/switch/close) wired via executor and Playwright. Contract tests for each primitive; e2e for select/upload/drag and drop/tab switching.
- **Tests:** Contract plus integration (deterministic fixtures) for dropdown select, drag and drop, upload, tab switching; zero flake budget.

1c) Robust waits and conditions - STATUS: [X]

- **DoD:** unified wait helpers implemented and wired via `WaitFor` handler: element visible/clickable/hidden/text; URL contains; network idle; animation frame; sleep.
- **Tests:** Contract for each wait; deterministic e2e using data: URLs for visible/text/urlContains/sleep/raf; network idle covered by contract.

1d) Downloads and basic artifacts - STATUS: [X]

- **DoD:** download file and verify (existence plus sha256) via artifacts; element screenshot already present; artifacts store lists `download/<filename>` and serves bytes.
- **Tests:** Contract for handler checksum; e2e (Playwright) triggers deterministic download via data/blob and verifies presence plus checksum plus artifacts list.

2. Guardrails for planner plus rate limit - STATUS: [X]

   - **DoD:** `/api/plan/preview` enforces JSON-only with glue fallback, 429 on bursts, timeouts, few-shots added, and input caps.
   - **Tests:** API tests for 429 and glue path (`engine/tests/api/test_plan_preview_guardrails.py`).

3. Postgres migrations plus durable queue (Phase A) - STATUS: [X]

   - **DoD:** Schema for runs/steps/suites/queue/locator_profiles added; queue uses `SKIP LOCKED`; in-memory path preserved.
   - **Tests:** Integration for enqueue/claim/finish; idempotence; PG toggle (see `engine/tests/integration/test_postgres_storage_basic.py` and `test_postgres_queue_api.py`).

4. Runner agent and concurrency - STATUS: [X]

   - **DoD:** Multiple runners process jobs asynchronously (configurable via `RUNNER_CONCURRENCY`); queue supports `SKIP LOCKED` multi-claim; stale running jobs are requeued based on a lease timeout; metrics/OTel instrumentation reflect run counts and durations. Runner failures do not block the queue.
   - **Tests:** Integration sim multi-claim (`engine/tests/integration/test_pg_queue_multi_claim.py`); queue lease/timeout requeue (`engine/tests/integration/test_queue_lease_requeue_pg.py`); runner path defaults covered by live runner tests.

5. Portal basics: Runs list plus artifacts preview - STATUS: [X]

   - **DoD:** Shows latest runs, details, artifacts (log/screenshot links); NL run remains usable.
   - **Tests:** Route tests for proxies; CI sanity asserts non-empty list after sample run.

6. Docs cleanup and alignment - STATUS: [~]
   - **DoD:** Fix encoding in key docs, reformat `docs/PROJECT_GUIDE.md`, correct ADR-0003 header, README links to Observability/CI/Security/ADRs, and reference `CONTRACT.md` as the canonical test/run/PageBrain contract.
   - **Tests:** None; CI spell/format if configured.

---

### P1 - SaaS Foundations

7. Multi-tenant base schema - STATUS: [ ]

   - **DoD:** `tenants`/`users`/`api_keys` tables; `tenant_id` on runs/steps/suites/queue/artifacts; per-tenant metrics labels.
   - **Tests:** RBAC unit tests; isolation integration tests.

8. AuthN/Z MVP - STATUS: [ ]

   - **DoD:** API keys or JWT; protect admin/dev endpoints; rate-limit per key.
   - **Tests:** Auth success/deny; rate-limit.

9. Artifact storage and retention - STATUS: [~]

   - **DoD:** Switchable FS/S3/MinIO backend with retention policy; background pruning.
   - **Tests:** FS plus MinIO adapters; retention unit and integration tests.

10. Portal UX / runs dashboard - STATUS: [~]
    - **DoD:** Paginated runs list, filters, details, artifact previews; NL run remains usable.
    - **Tests:** FastAPI route tests; snapshot/e2e on basic flows.

10b) Contract wiring in Portal - STATUS: [~] - **DoD:** Portal uses `CONTRACT.md` structures for: - test creation/editing (step-based English model); - run detail views (step-level status, screenshots, basic PageBrain info); - stable IDs mapping Test ↔ Run ↔ StepRun. - **Tests:** Portal API tests verifying schema; snapshot tests for basic run views.

---

### P2 - Learning and Retrieval (Toward "Super Bot")

13. Profile learning and healing drift - STATUS: [X]

- **DoD:** Registrable domain normalization; deterministic tie-breakers; profile metrics (hit/miss); healing under UI drift.
- **Tests:** Healing drift scenarios (live debug plus CSS generalization); domain normalization unit; orchestrator saves and uses registrable domain.

14. Cross-site retrieval (opt-in, privacy-safe) - STATUS: [X]

- **DoD:** Element embeddings (DOM attributes plus text) stored (pgvector-ready via JSONB fallback); retrieval mixed into healer when local signals fail; automatic save on success; strict tenant isolation and opt-in global corpus.
- **Tests:** Embedding unit (cosine), PG-backed retrieval integration, privacy isolation (tenant/global opt-in).

14b) Retrieval v2 (pgvector plus small embeddings) - STATUS: [X]

- **DoD:** `pgvector` column plus ANN index (IVFFLAT/HNSW where available) on `retrieval_embeddings`, JSONB fallback kept; configurable embedder backend (hash or SBERT) with bounded cache; retrieval path remains mixed into healer with strict tenant isolation and opt-in global corpus, ready to be exercised by the planner.
- **Tests:** Embedding unit and PG retrieval plus privacy integration tests remain green; `pgvector` path exercised when extension is present; evaluation harness for lift stays under 15/15b.

14c) Planner intents and navigation/actions - STATUS: [X]

- **DoD:** planner/LLM understands core web navigation and manual-QA-style action intents ("go back", "reload the page", "scroll down a bit", "open the dashboard in a new tab", "switch to the second tab", "close this tab", "download the report", etc.) via an explicit tool vocabulary, prompt examples, and glue fallback; portal NL flows emit the correct navigation/scroll/action tools into engine plans; high-frequency QA commands are handled even when the LLM output is noisy.
- **Tests:** `/api/plan/preview` tests for navigation, tab, scroll, and download phrases plus correct tool calls; orchestrator tests for glue behavior, including tab/download intents; portal NL run tests remain green.

14d) Planner QA flows (forms/asserts/multi-step) - STATUS: [X]

- **DoD:** planner/LLM understands common manual-QA flows around forms and assertions and can emit small multi-step plans using existing tools, mapped cleanly to step-level semantics as defined in `CONTRACT.md`.
- **Tests:** `/api/plan/preview` tests for QA phrases in both glue and LLM modes; orchestrator tests for glue behavior on QA-style steps; prompt content tests; portal NL tests remain green.

14e) Planner traces and QA dataset - STATUS: [X]

- **DoD:** planner emits per-step traces into run JSONL logs (`planner.step` events with step text, planner path, and tool calls), and a small extractor turns those traces into a planner QA dataset JSONL under `reports/`. A curation step normalizes text, tags categories (forms/nav/asserts/errors/downloads/scroll), deduplicates near-identical examples, and produces stable train/dev splits ready for fine-tuning.
- **Tests:** Dataset extraction and curation unit tests (`engine/tests/eval/test_planner_dataset.py`, `test_planner_curation.py`); manual export via `python scripts/planner_export_qa_dataset.py` followed by `python scripts/planner_curate_qa_dataset.py` produces train/dev JSONL files under `reports/` for inspection.

14f) Planner training dataset contract - STATUS: [X]

- **DoD:** JSONL schema for planner training data is documented and stable (input: QA step text plus optional category; output: ordered tool calls with tool/args as a JSON array string); planner export + curation scripts always produce this schema (`planner_qa_train_export.jsonl`, `planner_qa_dev_export.jsonl`) and tests guard against schema drift.
- **Tests:** Schema-level unit tests over curated examples; snapshot/corpus tests that fail if required keys or field types change unexpectedly.

14g) Planner QA corpus >= 200 examples - STATUS: [X]

- **DoD:** Planner QA corpus expanded to at least 200 high-quality, labeled examples across forms, navigation, assertions, errors, downloads, and scroll flows; examples are deduplicated, categorized, and wired into the planner eval/ablation harness. Metrics by category are reported in CI artifacts.
- **Tests:** Corpus invariants (minimum size and per-category counts) in eval tests; ablation harness runs without flakiness.

14h) Planner LLM training/export integration - STATUS: [X]

- **DoD:** Export scripts produce a training-ready JSONL format from the curated corpus; basic hooks exist to evaluate a newly trained planner model via `/api/plan/preview` using the same QA eval harness, so we can compare tuned vs base models before flipping defaults.
- **Tests:** Unit tests for export formatting and schema; smoke-style test that plugs a fake "tuned" model into `/api/plan/preview` and drives it via the ablation harness helpers.

15. Evaluation harness and leaderboard - STATUS: [X]

- **DoD:** Offline, deterministic evaluation harness for snapshot element resolution is implemented (`engine.eval.harness` + `scripts/eval_harness.py`), with JSON/CSV reports under `reports/`; CI runs the harness via `make ci` so an eval report is always produced. A lightweight planner ablation harness compares glue vs LLM accuracy on a small QA corpus. Leaderboard/Grafana panels remain a future extension once metrics stabilize.
- **Tests:** Deterministic fixture tests for aggregation; planner ablation metrics tests; eval harness is wired into CI and remains non-flaky.

15b) Eval corpus expansion - STATUS: [~]

- **DoD:** Corpus expanded beyond the initial seed into a broader set of snapshot cases (controls, dialogs, lists/nav, drift variants, basic forms, shortcuts), each tagged with a category so by-category metrics are meaningful; still short of the long-term 20–30+ target and without hard "lift threshold" gating. Retrieval/healer behavior is exercised both offline (deterministic harness) and online against Postgres/pgvector via integration tests that seed multiple embeddings and assert the correct selector is ranked above distractors. Planner QA intents (nav, scroll, download, URL asserts, submit, error text) are covered by a regression corpus plus end-to-end QA live-run harness.
- **Tests:** Summary aggregation unit test plus corpus invariants; healer eval harness tests; planner QA eval tests; Postgres/pgvector integration tests for retrieval and privacy.
- **Progress:** Snapshot eval harness (`engine.eval.harness` + `scripts/eval_harness.py`) now carries a multi-category corpus (controls/dialogs/lists/forms/shortcuts/drift). Healer eval harness (`engine.eval.healer_retrieval` + `scripts/healer_eval_harness.py`) aggregates deterministic cases including retrieval hits; Postgres/pgvector integration tests seed embeddings and verify lift over distractors.

16. Observability per tenant - STATUS: [X]

- **DoD:** Tenant labels on core metrics (runs/steps). Added Grafana per-tenant dashboard and filters. Bounded label cardinality maintained.
- **Tests:** Step payload includes tenant label; visual validation via Grafana dashboard.

16b) PageBrain v1 – Heuristic + Retrieval Element Ranking - STATUS: [X]

- **DoD:** First-class `PageBrain` module sits between planner and executor. Given a step, current DOM, and selector profiles, it returns the best selector candidate using:
  - text similarity;
  - tag/role/aria/data-\* features;
  - domain-normalized profiles;
  - retrieval scores from embeddings.
    Healer remains as fallback when PageBrain’s choice fails.
- **Progress:** `PageBrainResolver` (heuristic + profiles/retrieval stub) wraps the resolver, surfaces per-action PageBrain metadata into executor `meta`, and emits `pagebrain.choice` events for dataset export.
- **Tests:** Deterministic fixtures for DOM snapshots that assert the correct element is ranked first; integration tests for planner → PageBrain → executor path (with healer off and on), using the `StepRun`/`ActionRun` shapes from `CONTRACT.md`.

16c) PageBrain action logging and dataset export - STATUS: [X]

- **DoD:** For each actionable step, engine logs a structured record as in `CONTRACT.md` (ActionRun + PageBrain + Healer fields). Scripts export curated JSONL datasets (`pagebrain_train.jsonl`, `pagebrain_dev.jsonl`) with a stable schema for training and evaluation.
- **Progress:** Executor emits `action.run` events with tool/ok/reason + PageBrain/Healer metadata; exporters/curators produce `pagebrain_dataset.jsonl` (with candidates + labels) and train/dev splits + training exports.
- **Tests:** Schema/unit tests for logging/export/curation; integration tests for logging flow into datasets.

16d) PageBrain ML Ranker (GBM-style) - STATUS: [X]

- **DoD:** Training pipeline for a gradient-boosted ranking model (e.g. LightGBM/XGBoost) over PageBrain features. Offline eval harness computes top-1 / top-k / MRR on the curated dataset and compares multiple candidate models (including heuristic baseline). The selected model is packaged as a versioned artifact and wired as the primary scorer inside PageBrain, with a config flag to fall back to heuristic-only mode.
- **Progress:** Candidate features are extracted and stored in datasets; `engine/eval/pagebrain_ranker.py` now builds feature matrices, runs a LightGBM ranking pass when available (with fallback baseline), and reports top-1/top-k/MRR. Eval script (`scripts/pagebrain_ranker_eval.py`) consumes the train/dev exports and reports baseline vs model metrics plus lift on the dev set, and emits a simple linear weights file at `reports/pagebrain_model_weights.json` that can be referenced by `KAIZEN_PAGEBRAIN_DEFAULT_MODEL` / `KAIZEN_PAGEBRAIN_MODELS` for runtime scoring.
- **Tests:** Unit tests for feature extraction/baseline/GBM scaffolding (`engine/tests/pagebrain/test_pagebrain_ranker.py`); exporter/curator tests ensure features exist.

16e) Tenant-isolated PageBrain models - STATUS: [X]

- **DoD:** Per-tenant model storage and selection: PageBrain can load a global default model and optionally a tenant-specific model trained on that tenant’s logs only. Model selection and retrieval strictly respect tenant boundaries; no cross-tenant data or embeddings are used. Fallback behavior is defined for tenants without a trained model (use global model + heuristics).
- **Progress:** Model store stub added with per-tenant overrides; resolver accepts tenant context and records model_id in PageBrain metadata (wiring ready for future model loading).
- **Tests:** Multi-tenant tests that assert model isolation; tests that verify correct fallback; privacy tests confirming that training data and model artifacts never mix tenant IDs.

16f) PerceptionLayer & Screenshot Diff v1 (3-layer visual diff) - STATUS: [ ]

- **DoD:** Introduce a `PerceptionLayer` abstraction inside the engine (e.g. `engine/core/perception`) wired by DI, responsible for combining DOM snapshots + screenshots into structured visual signals:
  - 3-layer diff metrics per action:
    - `element_region_diff` — diff of the bounding-box crop around the target element (with small padding).
    - `main_region_diff` — diff of a viewport / main-content region (e.g. below header, or an expanded region around the target).
    - `full_page_diff` — diff of the entire screenshot.
  - Deterministic implementation only (no ML): pixel-level difference and/or SSIM on PNGs; stable, bounded CPU cost.
- PerceptionLayer receives:
  - `dom_snapshot_id` (or DOM slice reference),
  - before/after screenshot paths,
  - optional target element bounding box from the browser adapter.
- PerceptionLayer returns a small DTO (e.g. `ScreenshotDiff`) that the executor attaches to `ActionRun.meta` and exports with artifacts.
- Metrics are plumbed to OTel/Prometheus with **bounded cardinality** (e.g. histograms for diff scores, counters per tool type).
- This layer is **pure infra**: no behavior change yet, only additional signals and metrics.
- **Tests:**
  - Unit tests for diff computation (element/main/full) with deterministic image fixtures.
  - Integration tests ensuring `ActionRun` JSON includes the perception diff block and that missing screenshots/DOM are handled gracefully (no crashes, safe defaults).

16g) Outcome Validation v1 – DOM + Perception metrics - STATUS: [ ]

- **DoD:** Add an `OutcomeAssessment` concept and an `OutcomeDetector` component that classifies each step/action as `succeeded`/`failed`/`unknown` using:
  - Tool type (`click`, `type`, `press`, `waitFor`, asserts, etc.).
  - DOM-based signals:
    - value/text changes for inputs,
    - visibility/role changes,
    - URL changes,
    - explicit assertion results.
  - PerceptionLayer metrics:
    - `element_region_diff`, `main_region_diff`, `full_page_diff`.
    - Simple thresholds to distinguish local vs large layout changes vs no visible change.
- Minimal pattern-based use of `Step.expected` (from `CONTRACT.md`) without LLM:
  - Recognize a small DSL over English like:
    - "URL contains '...'"
    - "field 'X' contains 'Y'"
    - "text 'Y' appears on the page"
    - "element 'X' is visible"
  - Compile these into explicit internal assertions (`assertUrlContains`, `assertText`, `assertVisible`) that run after the last tool call for the step.
- Extend `StepRun` (and optionally `ActionRun`) with an `outcome` block:
  - `status`: `"succeeded" | "failed" | "unknown"`.
  - `reasons`: small list of human-readable strings.
  - `metrics`: embedded diff and DOM-change metrics (for debugging and future training).
- Wire OutcomeDetector via DI so it can be swapped or disabled (e.g. config flag).
- **Tests:**
  - Unit tests over synthetic DOM/screenshot cases for `click`, `type`, `waitFor`, assertions to verify correct classification.
  - Contract-style regression tests ensuring step `status` and `outcome` are consistent for basic flows (login, search, form submit).
  - Backwards-compatibility tests: existing runs that ignore `outcome` continue to pass.

16h) PageBrain v2 – Perception-aware ranking (DOM + Perception + optional vision) - STATUS: [ ]

- **DoD:** Extend PageBrain’s scoring interface so that, for each candidate element, it can consume PerceptionLayer/vision-derived features in addition to existing DOM/retrieval features:
  - Shape:
    - DOM features (tag, text, attributes, roles, profiles, retrieval scores).
    - Optional perception/vision features (behind flags), e.g.:
      - `looks_like_button`, `looks_like_input`, `looks_clickable`.
      - `vision_text` (short caption for the element crop).
  - Keep PageBrain’s core responsibilities unchanged: **rank candidates and pick one**; PerceptionLayer remains a dependency injected service, not a hard-coded call.
- First step focuses on **lightweight improvements**:
  - Use pre-trained text embeddings and/or small local vision/caption models (if enabled) only for **feature generation**, not for end-to-end decision.
  - If vision is disabled, PageBrain still works with DOM-only features (current behavior).
- The GBM ranker is **not retrained** in this step; we:
  - Log new perception/vision features alongside existing ones into the PageBrain dataset.
  - Ensure the eval harness can report metrics segmented by “perception enabled/disabled” and by feature availability.
- PageBrain v2 behavior must be **configurable**:
  - `KAIZEN_PAGEBRAIN_USE_PERCEPTION=true|false`
  - `KAIZEN_PAGEBRAIN_USE_VISION=true|false`
- **Tests:**
  - Unit tests for PageBrain feature extraction when perception is on/off.
  - Regression tests verifying existing deterministic DOM-only fixtures still pass with `USE_PERCEPTION=false`.
  - New fixtures where DOM is ambiguous but a perception/vision hint (e.g. “looks like button”) lifts the correct candidate; harness reports improved top-1 where enabled.

16i) Perception & Outcome Feedback Loop – datasets and eval - STATUS: [ ]

- **DoD:** Extend logging and dataset export to capture perception and outcome signals for future training and analysis:
  - `ActionRun` and `StepRun` logs include:
    - Perception diff metrics (3-layer scores).
    - OutcomeAssessment (`status`, `reasons`, `metrics`).
  - New dataset exports under `reports/`:
    - `perception_outcome_dev.jsonl`, `perception_outcome_train.jsonl` (or similar) with:
      - step text, expected, tool calls,
      - DOM features,
      - perception metrics,
      - final outcome label.
- Update eval harness (or add a small one) to:
  - Report correlation between perception metrics and pass/fail outcomes.
  - Surface where outcome classification disagrees with explicit assertions (for debugging).
- Ensure strict tenant isolation:
  - Perception/Outcome datasets carry `tenant_id`.
  - No cross-tenant mixing in exports; opt-in for any cross-tenant/global analysis.
- **Tests:**
  - Schema tests for new datasets (stable JSONL contract).
  - Integration test from a small live run → exported dataset → basic aggregation (no flakiness in CI).
  - Privacy tests that assert tenant IDs are preserved and not merged.

---

### P3 - Cloud Scale and UX

17. Kubernetes plus Helm (cloud ready) - STATUS: [~]

- **DoD (phase 1):** Helm chart (API, runner, portal, Postgres, OTEL) plus runner HPA; dev README; kind/Minikube smoke capable.
- **Tests:** Helm template renders; manual smoke deploy via README.

18. Portal v2 (Next.js/React UI) - STATUS: [ ]

- **DoD:** Auth, test editor, run viewer, artifact gallery, model selection, settings; backend stays FastAPI and speaks the contract defined in `CONTRACT.md`.
- **Tests:** API route tests; UI Playwright tests (local).

19. Security and compliance - STATUS: [ ]

- **DoD:** Audit logs; encryption at rest and in transit; backups; incident playbooks; data retention policies.
- **Tests:** Audit log unit; backup/restore (non-prod data); security scanning in CI.

20. Billing and quotas (SaaS) - STATUS: [ ]

- **DoD:** Usage tracking per tenant; soft quotas; Stripe integration behind flag.
- **Tests:** Usage counters; mock billing tests.

21. Vision assist (flagged, optional) - STATUS: [ ]

- **DoD:** Build on the PerceptionLayer and PageBrain v2 hooks to optionally enable a local VLM-backed vision service (pre-trained, no custom training) for:
  - region proposals and last-resort element hints when PageBrain + Healer fail;
  - richer before/after captions for step descriptions in the portal;
  - strictly rate-limited, disabled by default, controlled by config/env flags (e.g. `KAIZEN_VISION_ENABLED`).
    Vision assist must **not** be required for correctness: core behavior (DOM + PerceptionLayer diff + PageBrain + Healer) remains fully functional without it.
- **Tests:** Adapter and gating tests for the vision service; tests verifying that when vision is disabled all flows still work; smoke tests for a local-caption path over a handful of screenshots (offline fixture).

---

## Notes on "Super Bot" Element Finding and Planning

- Sequence: Planner/LLM decides **what** to do in QA terms; PageBrain ranks **where** to act using heuristics plus profiles plus retrieval (pgvector) plus, later, a GBM ranker and optional visual hints; Healer remains the safety net for the remaining failures and feeds back into learning. PerceptionLayer and outcome validation add a **self-check** loop via DOM + visual diff + optional vision, improving both PageBrain training data and runtime confidence.
- Tests and runs follow the step-based, hybrid-planning contract defined in `CONTRACT.md`:
  - QA steps are first-class;
  - planner runs per step with full-test context;
  - logs and datasets are aligned to `Test` → `Step` → `StepRun` → `ActionRun`.
- PageBrain datasets are built only from high-confidence steps (strong success signals or curated fixtures); ambiguous steps are excluded from training to avoid teaching on bad labels. OutcomeAssessment plus PerceptionLayer metrics become additional “success signal” inputs over time.
- Privacy: strict tenant isolation; separate, anonymized opt-in corpus only when explicitly enabled. Global models may be trained from public/demo data and/or opt-in anonymized patterns, but tenant-specific models train only on that tenant’s logs.
- Before custom fine-tuning of large models, try lightweight models (GBMs) over structured features for PageBrain; only consider heavier neural models once evaluation data justifies the additional complexity and cost. Vision assist is **feature generation and last-resort guidance**, not a replacement for deterministic DOM logic.

**Mobile scope:** explicitly deferred. Focus on desktop web primitives to 100 percent reliability before attempting mobile gestures.

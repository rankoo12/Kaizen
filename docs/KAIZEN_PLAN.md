Kaizen - End Goal, Status, and Strict Plan

Legend: [X] Done  [~] Planned/In Progress  [ ] Not Started  (*) Vision/Goal

End Goal (*)
- QA writes plain English tests and runs them locally and in the cloud (SaaS).
- The Engine plans and executes via Playwright first (adapters allow Selenium/WebDriver BiDi later), resolves elements robustly, and heals selectors.
- The Portal is a multi-tenant app for authoring tests, launching runs, reviewing artifacts and metrics, managing models, and connecting repos.
- Kaizen "learns" over time: cross-site retrieval uses embeddings, profiles, heuristics, and vision to approach near-100% element finding, with strong privacy and tenant isolation.

Current Status Snapshot
- Engine ([X]): FastAPI API/CLI; orchestrator + deterministic plan executor; DOM resolver v1; handlers for open/click/type/press.
- Engine extensions ([X]): Added handlers for wait/assert/custom; wiring and tests included in this change.
- Storage ([X]): In-memory + Postgres backend; settings + DI; basic profiles persisted.
- Portal ([~]): Thin backend with minimal HTML page; NL run; runs polling; artifacts view basics.
- Infra/CI ([X]): Docker Compose; Jenkins pipeline via scripts/ci.sh; OTel + Prometheus/Grafana/Jaeger.
- Security ([X]): Safe URL allow-list, schema validation, local LLM via Ollama; structured logs; no secrets in repo.

What Is Missing or To Add
- Action Coverage ([~]): waitFor/assertVisible/assertText/assertUrl/custom are implemented with unit tests; future polish as needed.
- Migrations/Indexes ([~]): Alembic plus indexes per ADR-0006; durable queue on Postgres.
- Portal UX ([~]): Runs list, details, artifact previews; later a proper React/Next.js UI.
- AuthN/Z and Tenancy ([ ]): API keys or JWT, tenants/users, RBAC, per-tenant isolation.
- Artifact Storage ([~]): FS default; optional S3/MinIO; retention policy.
- Learning and Retrieval ([~]): pgvector-based embeddings; retrieval-augmented resolve; opt-in global corpus.
- Multi-browser ([ ]): Selenium/WebDriver BiDi adapter via IBrowser.
- Scheduler ([ ]): Suite CRUD plus periodic runs.
- Cloud ([ ]): Helm/Kubernetes, HPA for runners; Terraform for dev env.
- Compliance ([ ]): Audit logs, backups, data retention, billing/quotas.

Strict, Test-First Plan

P0 - Reliability First
1) Implement missing handlers (wait/assert/custom) - STATUS: [X]
   - DoD: waitFor/assertVisible/assertText/assertUrl/custom handlers wired in DI and executor target resolution; README examples added later.
   - Tests: Unit per handler; simple integration via executor can follow.

1b) Core actions completeness (desktop web only) - STATUS: [X]
   - DoD: click/double-click/context-click/hover/focus/blur/type/clear/select(dropdown)/upload file/drag and drop; scroll to/up/down/left/right; reload/back/forward; open/close/switch tab or window.
   - Delivered: all action primitives plus navigation (reload/back/forward/new tab/window/switch/close) wired via executor and Playwright. Contract tests for each primitive; e2e for select/upload/drag and drop/tab switching.
   - Tests: Contract plus integration (deterministic fixtures) for dropdown select, drag and drop, upload, tab switching; zero flake budget.

1c) Robust waits and conditions - STATUS: [X]
   - DoD: unified wait helpers implemented and wired via WaitFor handler: element visible/clickable/hidden/text; URL contains; network idle; animation frame; sleep.
   - Tests: Contract for each wait; deterministic e2e using data: URLs for visible/text/urlContains/sleep/raf; network idle covered by contract.

1d) Downloads and basic artifacts - STATUS: [X]
   - DoD: download file and verify (existence plus sha256) via artifacts; element screenshot already present; artifacts store lists "download/<filename>" and serves bytes.
   - Tests: Contract for handler checksum; e2e (Playwright) triggers deterministic download via data/blob and verifies presence plus checksum plus artifacts list.

2) Guardrails for planner plus rate limit - STATUS: [X]
   - DoD: "/api/plan/preview" enforces JSON-only with glue fallback, 429 on bursts, timeouts, few-shots added, and input caps.
   - Tests: API tests for 429 and glue path ("engine/tests/api/test_plan_preview_guardrails.py").

3) Postgres migrations plus durable queue (Phase A) - STATUS: [X]
   - DoD: Schema for runs/steps/suites/queue/locator_profiles added; queue uses SKIP LOCKED; in-memory path preserved.
   - Tests: Integration for enqueue/claim/finish; idempotence; PG toggle (see "engine/tests/integration/test_postgres_storage_basic.py" and "test_postgres_queue_api.py").

4) Runner agent and concurrency - STATUS: [~]
   - DoD: Multiple runners process jobs; requeue on worker death; metrics reflect queue depth.
   - Tests: Integration sim multi-claim; timeouts/abort.

5) Portal basics: Runs list plus artifacts preview - STATUS: [~]
   - DoD: Shows latest runs, details, artifacts (log/screenshot links); NL run remains usable.
   - Tests: Route tests for proxies; CI sanity asserts non-empty list after sample run.

6) Docs cleanup and alignment - STATUS: [~]
   - DoD: Fix encoding in key docs, reformat "docs/PROJECT_GUIDE.md", correct ADR-0003 header, README links to Observability/CI/Security/ADRs.
   - Tests: None; CI spell/format if configured.

P1 - SaaS Foundations
7) Multi-tenant base schema - STATUS: [ ]
   - DoD: "tenants"/"users"/"api_keys" tables; tenant_id on runs/steps/suites/queue/artifacts; per-tenant metrics labels.
   - Tests: RBAC unit tests; isolation integration tests.

8) AuthN/Z MVP - STATUS: [ ]
   - DoD: API keys or JWT; protect admin/dev endpoints; rate-limit per key.
   - Tests: Auth success/deny; rate-limit.

9) Artifact storage and retention - STATUS: [~]
   - DoD: Switchable FS/S3/MinIO backend with retention policy; background pruning.
   - Tests: FS plus MinIO adapters; retention unit and integration tests.

10) Portal UX / runs dashboard - STATUS: [~]
   - DoD: Paginated runs list, filters, details, artifact previews; NL run remains usable.
   - Tests: FastAPI route tests; snapshot/e2e on basic flows.

P2 - Learning and Retrieval (Toward "Super Bot")
13) Profile learning and healing drift - STATUS: [X]
   - DoD: Registrable domain normalization; deterministic tie-breakers; profile metrics (hit/miss); healing under UI drift.
   - Tests: Healing drift scenarios (live debug plus CSS generalization); domain normalization unit; orchestrator saves and uses registrable domain.

14) Cross-site retrieval (opt-in, privacy-safe) - STATUS: [X]
   - DoD: Element embeddings (DOM attributes plus text) stored (pgvector-ready via JSONB fallback); retrieval mixed into healer when local signals fail; automatic save on success; strict tenant isolation and opt-in global corpus.
   - Tests: Embedding unit (cosine), PG-backed retrieval integration, privacy isolation (tenant/global opt-in).

14b) Retrieval v2 (pgvector plus small embeddings) - STATUS: [X]
   - DoD: pgvector column plus ANN index (IVFFLAT/HNSW where available) on "retrieval_embeddings", JSONB fallback kept; configurable embedder backend (hash or SBERT) with bounded cache; retrieval path remains mixed into healer with strict tenant isolation and opt-in global corpus, ready to be exercised by the planner.
   - Tests: Embedding unit and PG retrieval plus privacy integration tests remain green; pgvector path exercised when extension is present; evaluation harness for lift stays under 15/15b.

14c) Planner intents and navigation/actions - STATUS: [X]
   - DoD: planner/LLM understands core web navigation and manual-QA-style action intents ("go back", "reload the page", "scroll down a bit", "open the dashboard in a new tab", "switch to the second tab", "close this tab", "download the report", etc.) via an explicit tool vocabulary, prompt examples, and glue fallback; portal NL flows emit the correct navigation/scroll/action tools into engine plans; high-frequency QA commands are handled even when the LLM output is noisy.
   - Tests: "/api/plan/preview" tests for navigation, tab, scroll, and download phrases plus correct tool calls; orchestrator tests for glue behavior, including tab/download intents; portal NL run tests remain green.

15) Evaluation harness and leaderboard - STATUS: [X]
   - DoD: Offline, deterministic evaluation harness for snapshot element resolution is implemented (engine.eval.harness + scripts/eval_harness.py), with JSON/CSV reports under "reports/"; CI runs the harness via "make ci" so an eval report is always produced. Leaderboard/Grafana panels remain a future extension once metrics stabilize.
   - Tests: Deterministic fixture tests for aggregation ("engine/tests/eval/test_eval_aggregate.py"); eval harness is wired into CI and remains non-flaky.

15b) Eval corpus expansion - STATUS: [~]
   - DoD: Seed corpus of snapshot cases (controls, dialogs, lists, basic drift/form variants) defined via EvalCase in "engine.eval.harness", with per-case categories and summary by-category metrics; further expansion toward 20-30 scenarios and stricter lift thresholds is deferred.
   - Tests: Summary aggregation unit test; future integration run will produce stable metrics once corpus is expanded further.

16) Observability per tenant - STATUS: [X]
   - DoD: Tenant labels on core metrics (runs/steps). Added Grafana per-tenant dashboard and filters. Bounded label cardinality maintained.
   - Tests: Step payload includes tenant label; visual validation via Grafana dashboard.

P3 - Cloud Scale and UX
17) Kubernetes plus Helm (cloud ready) - STATUS: [~]
   - DoD (phase 1): Helm chart (API, runner, portal, Postgres, OTEL) plus runner HPA; dev README; kind/Minikube smoke capable.
   - Tests: Helm template renders; manual smoke deploy via README.

18) Portal v2 (Next.js/React UI) - STATUS: [ ]
   - DoD: Auth, test editor, run viewer, artifact gallery, model selection, settings; backend stays FastAPI.
   - Tests: API route tests; UI Playwright tests (local).

19) Security and compliance - STATUS: [ ]
   - DoD: Audit logs; encryption at rest and in transit; backups; incident playbooks; data retention policies.
   - Tests: Audit log unit; backup/restore (non-prod data); security scanning in CI.

20) Billing and quotas (SaaS) - STATUS: [ ]
   - DoD: Usage tracking per tenant; soft quotas; Stripe integration behind flag.
   - Tests: Usage counters; mock billing tests.

21) Vision assist (flagged, optional) - STATUS: [ ]
   - DoD: VLM-assisted region proposals as last-resort fallback; rate-limited; disabled by default.
   - Tests: Adapter and gating tests; not in default path.

Notes on "Super Bot" Element Finding and Planning
- Sequence: heuristics plus profiles plus retrieval (pgvector) plus visual hints (flagged). Measure lift at each step.
- Planner/LLM is the primary interface for manual-QA-style flows: it should reliably map common QA phrases (click, type, select, upload, drag/drop, scroll, simple waits, navigation) onto the existing tool vocabulary, and degrade gracefully via glue when outputs are noisy.
- Privacy: strict tenant isolation; separate, anonymized opt-in corpus only when explicitly enabled.
- Before custom training, try lightweight models (GBMs) over features; only consider fine-tuning once evaluation data justifies it.

Mobile scope: explicitly deferred. Focus on desktop web primitives to 100 percent reliability before attempting mobile gestures.

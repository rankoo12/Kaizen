Kaizen — End Goal, Status, and Strict Plan

Legend: 🟩 Done  🟨 Planned/In Progress  🟥 Not Started  🔵 Vision/Goal

End Goal (🔵)
- QA writes plain English tests and runs them locally and in the cloud (SaaS).
- The Engine plans and executes via Playwright first (adapters allow Selenium/WebDriver BiDi later), resolves elements robustly, and heals selectors.
- The Portal is a multi-tenant app for authoring tests, launching runs, reviewing artifacts/metrics, managing models, and connecting repos.
- Kaizen “learns” over time: cross-site retrieval uses embeddings/profiles/heuristics/vision to approach near-100% element finding, with strong privacy and tenant isolation.

Current Status Snapshot
- Engine (🟩): FastAPI API/CLI; orchestrator + deterministic plan executor; DOM resolver v1; handlers for open/click/type/press.
- Engine (🟨): Added handlers for wait/assert/custom; wiring and tests included in this change.
- Storage (🟩): In-memory + Postgres backend; settings + DI; basic profiles persisted.
- Portal (🟨): Thin backend with minimal HTML page; NL run; runs polling; artifacts view basics.
- Infra/CI (🟩): Docker Compose; Jenkins pipeline via scripts/ci.sh; OTel + Prometheus/Grafana/Jaeger.
- Security (🟩): Safe URL allow-list, schema validation, local LLM via Ollama; structured logs; no secrets in repo.

What’s Missing or To Add
- Action Coverage (🟨): waitFor/assertVisible/assertText/assertUrl/custom — now implemented with unit tests; future polish as needed.
- Migrations/Indexes (🟨): Alembic + indexes per ADR‑0006; durable queue on Postgres.
- Portal UX (🟨): Runs list, details, artifact previews; later a proper React/Next.js UI.
- AuthN/Z + Tenancy (🟥): API keys/JWT, tenants/users, RBAC, per-tenant isolation.
- Artifact Storage (🟨): FS default; optional S3/MinIO; retention policy.
- Learning/Retrieval (🟥): pgvector-based embeddings; retrieval‑augmented resolve; opt‑in global corpus.
- Multi-browser (🟥): Selenium/WebDriver BiDi adapter via IBrowser.
- Scheduler (🟥): Suite CRUD + periodic runs.
- Cloud (🟥): Helm/Kubernetes, HPA for runners; Terraform for dev env.
- Compliance (🟥): Audit logs, backups, data retention, billing/quotas.

Strict, Test‑First Plan

P0 — Reliability First
1) Implement missing handlers (wait/assert/custom) — STATUS: 🟩
   - DoD: waitFor/assertVisible/assertText/assertUrl/custom handlers wired in DI and executor target resolution; README examples added later.
   - Tests: Unit per handler; simple integration via executor can follow.

2) Guardrails for planner + rate limit — STATUS: 🟨
   - DoD: `/api/plan/preview` enforces JSON-only with glue fallback, 429 on bursts, timeouts.
   - Tests: Validator unit tests; API tests for 429 and glue path.

3) Postgres migrations + durable queue (Phase A) — STATUS: 🟨
   - DoD: Alembic creates runs/steps/suites/queue/selectors with indexes; queue uses SKIP LOCKED; in-memory path preserved.
   - Tests: Integration for enqueue/claim/finish; idempotence; PG toggle.

4) Runner agent and concurrency — STATUS: 🟨
   - DoD: Multiple runners process jobs; requeue on worker death; metrics reflect queue depth.
   - Tests: Integration sim multi-claim; timeouts/abort.

5) Portal basics: Runs list + artifacts preview — STATUS: 🟨
   - DoD: Shows latest runs, details, artifacts (log/screenshot links); NL run remains usable.
   - Tests: Route tests for proxies; CI sanity asserts non-empty list after sample run.

6) Docs cleanup and alignment — STATUS: 🟨
   - DoD: Fix encoding, reformat `docs/PROJECT_GUIDE.md`, correct ADR‑0003 header, README links to Observability/CI/Security/ADRs.
   - Tests: None; CI spell/format if configured.

P1 — SaaS Foundations
7) Multi-tenant base schema — STATUS: 🟥
   - DoD: tenants/users/api_keys tables; tenant_id on runs/steps/suites/queue/artifacts; per-tenant metrics labels.
   - Tests: RBAC unit tests; isolation integration tests.

8) AuthN/Z MVP — STATUS: 🟥
   - DoD: API keys or JWT; protect admin/dev endpoints; rate-limit per key.
   - Tests: Auth success/deny; rate-limit.

9) Artifact storage and retention — STATUS: 🟨
   - DoD: S3/MinIO with pre-signed URLs; FS default; retention by age/size.
   - Tests: MinIO integration (opt-in); retention policy unit tests.

10) Source code connectors (repo ingestion v1) — STATUS: 🟥
   - DoD: GitHub App integration; ingest repo metadata to build a “component dictionary” for resolver hints.
   - Tests: Connector unit tests (mock GitHub); resolver prefers known selectors.

11) Multi-browser support (adapter) — STATUS: 🟥
   - DoD: IBrowser pluggable; Selenium/WebDriver BiDi adapter; smoke runs in both.
   - Tests: Adapter API unit; e2e smoke in both drivers for a basic spec.

12) Test suite CRUD and scheduling — STATUS: 🟥
   - DoD: CRUD for suites/tests/variables; scheduled runs; secure secret handling.
   - Tests: API tests; masked secrets in logs; scheduler integration.

P2 — Learning & Retrieval (Toward “Super Bot”)
13) Profile learning polish — STATUS: 🟨
   - DoD: Registrable domain normalization; deterministic tie‑breakers; profile metrics (hit/miss).
   - Tests: Domain parsing unit; orchestrator asserts stable profile preference.

14) Cross-site retrieval (opt-in, privacy-safe) — STATUS: 🟥
   - DoD: Element embeddings (DOM attrs + text) stored in pgvector; retrieval mixed into resolver when local signals fail; strict tenant isolation and opt‑in global corpus.
   - Tests: Embedding generation unit; integration showing lift on held-out site; privacy tests.

15) Evaluation harness and leaderboard — STATUS: 🟥
   - DoD: Corpus + breakage scenarios; success@1/@3, healing rate, TTR; artifacts and Grafana panels.
   - Tests: Deterministic fixture tests; CI produces eval report.

16) Observability per tenant — STATUS: 🟥
   - DoD: Dashboards filtered by tenant; bounded label cardinality; SLOs (run failure rate, p95 step).
   - Tests: Metric label tests; CI sanity against labeled run.

P3 — Cloud Scale & UX
17) Kubernetes + Helm (cloud ready) — STATUS: 🟥
   - DoD: Helm chart (API, runner, portal, Postgres, MinIO, optional Redis); HPA for runners; Terraform dev env.
   - Tests: Helm template lint; smoke deploy in kind/Minikube; sanity run passes.

18) Portal v2 (Next.js/React UI) — STATUS: 🟥
   - DoD: Auth, test editor, run viewer, artifact gallery, model selection, settings; backend stays FastAPI.
   - Tests: API route tests; UI Playwright tests (local).

19) Security & compliance — STATUS: 🟥
   - DoD: Audit logs; encryption at rest/in transit; backups; incident playbooks; data retention policies.
   - Tests: Audit log unit; backup/restore (non-prod data); security scanning in CI.

20) Billing & quotas (SaaS) — STATUS: 🟥
   - DoD: Usage tracking per tenant; soft quotas; Stripe integration behind flag.
   - Tests: Usage counters; mock billing tests.

21) Vision assist (flagged, optional) — STATUS: 🟥
   - DoD: VLM-assisted region proposals as last-resort fallback; rate-limited; disabled by default.
   - Tests: Adapter and gating tests; not in default path.

Notes on “Super Bot” Element Finding
- Sequence: heuristics → profiles → retrieval (pgvector) → visual hints (flagged). Measure lift at each step.
- Privacy: strict tenant isolation; separate, anonymized opt‑in corpus only when explicitly enabled.
- Before custom training, try lightweight models (GBMs) over features; only consider fine-tuning once evaluation data justifies it.

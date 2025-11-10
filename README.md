Kaizen ׳’ג‚¬ג€ Engine + Portal (Current Status)

Overview
- Monorepo with a deterministic web test engine (FastAPI) and a minimal portal backend.
- Goal: Manual QA can type plain English, run tests live or snapshot, and review results with metrics and healing.

Quick Start
- Docker (recommended):
  - Start services: `docker compose -f infra/docker-compose.yml up -d`
  - Open Engine API docs: http://localhost:8080/api/docs
  - Open Portal API (simple UI served at root): http://localhost:8081/
  - Open Grafana (Observability): http://localhost:3000 (admin/admin)
  - Open Prometheus: http://localhost:9090
  - Open Jaeger: http://localhost:16686
  - Optional (LLM via local Ollama):
    - Install and run Ollama on your host machine (listens on `http://localhost:11434`).
    - In compose, set (engine-api and runner): `KAIZEN_LLM_ENABLED=true`, `KAIZEN_PLANNER_PATH=llm`, and `KAIZEN_OLLAMA_BASE_URL=http://host.docker.internal:11434`.
    - Pull a model locally on your host: `ollama pull llama3.1`.

Key Environment Variables (all map from KAIZEN_* to Settings)
- LLM/Planner
  - `KAIZEN_LLM_ENABLED=true` to enable LLM endpoints and live planning.
  - `KAIZEN_PLANNER_PATH=llm` to use LLM for live step planning (glue fallback on errors).
  - `KAIZEN_OLLAMA_BASE_URL=http://host.docker.internal:11434`, `KAIZEN_OLLAMA_MODEL=llama3.1` (when using local Ollama).
- Live navigation policy
  - `KAIZEN_ALLOWED_URL_SCHEMES=https://,http://,about:blank,data:` (comma-separated).
  - Defaults restrict to `about:blank` and `data:`; explicitly add `https://,http://` when you want to navigate in live runs.
 - Browser/Timeouts
   - `KAIZEN_PW_TIMEOUT_MS=10000` default per-action timeout (ms). Lower to fail faster (e.g., 5000).
   - `KAIZEN_PW_NAV_TIMEOUT_MS=15000` navigation timeout (ms).
   - `KAIZEN_NAV_WAIT=domcontentloaded|load|networkidle` wait policy for `open()` and reloads.
   - `KAIZEN_HEADFUL=true` to run the browser visibly for debugging.
- Healer
 - Engine Caps
   - `KAIZEN_RUN_TIMEOUT_MS` optional run-level cap (ms). Aborts remaining steps with reason `timeout_run`.
   - `KAIZEN_EXEC_STEP_TIMEOUT_MS` optional soft per-step cap (currently applied to resolve polling only).
  - `KAIZEN_HEALER_ENABLED=true` to enable selector healing.
  - `KAIZEN_HEALER_PATH=deterministic` (or `llm` for LLM-assisted proposals).
- Storage
  - `KAIZEN_STORAGE_BACKEND=auto|in_memory|postgres` (auto selects Postgres if `KAIZEN_PG_DSN` set).
  - `KAIZEN_PG_DSN=postgresql://user:pass@host:5432/db`.

End-to-End Flow (Author ׳’ג€ ג€™ Run ׳’ג€ ג€™ Heal ׳’ג€ ג€™ Learn ׳’ג€ ג€™ Review)
0) Preconditions
- Engine/Portal run via Docker; DI wiring in `engine/core/config/container.py`.
- LLM via Ollama; outbound network not required.
- Storage: In-memory default; Postgres supported with profiles/runs tables (created automatically).
- Plan schemas validated; CI tests pass locally.

1) Authoring
- Portal backend supports a natural language run: `POST /tests/nl-run` with `{url, stepsText}`.
- Steps are one per line; backend builds a TestSpec and enqueues a live run.
- LLM plan preview for tooling exists at Engine: `POST /api/plan/preview` (JSON-only result, schema-validated).

2) Launching a Run
- Engine queue: `POST /api/queue/runs` enqueues a job; runner picks it up.
- Engine also supports direct: `POST /api/runs` for immediate execution (snapshot/live).

3) Execution
- Orchestrator converts step text to validated tool calls (LLM with guardrails ׳’ג€ ג€™ glue fallback).
- DeterministicPlanExecutor resolves targets (resolver stub for now) and executes via Playwright.
- Click safety enforced (visible + enabled only).
- On failure, Healer attempts selector recovery (profile-assisted first, then heuristics).

4) Learning (Profiles)
- On successful click/type, Engine saves a locator profile:
  - `{ domain, tool, target_signature, selector, hits, last_seen }`.
  - Domain is extracted from the last `open()` URL. Lookup prefers domain match > global.

5) Artifacts & Metrics
- Reporter stores step/run rollups in-memory and (optionally) JSONL tail (`JsonlTailReporter`).
- Observability via OTel ׳’ג€ ג€™ Collector ׳’ג€ ג€™ Prometheus/Grafana:
  - Counters: `kaizen_runs_total`, `kaizen_runs_failed_total`.
  - Step histogram: `kaizen_step_duration_seconds`.
  - Queue gauge: `kaizen_queue_depth{state=queued|running}`.
  - Healing KPIs (when healing is enabled and triggered):
    - `kaizen_healer_attempts_total{strategy}`
    - `kaizen_healer_successes_total`
    - `kaizen_profile_hits_total`, `kaizen_profile_misses_total`.

6) Review
- Run details via Engine API: `GET /api/runs/{run_id}`.
- Portal run polling: `GET /runs/{jobId}` (portal backend proxy to engine queue/runs).
- Grafana dashboard: ׳’ג‚¬ֲKaizen Observability׳’ג‚¬ֲ panels include run rate, step p95, queue depth, and healing KPIs.

Current Capabilities
- LLM Planner Guardrails (live): strict JSON-only prompt, schema validation, glue fallback.
- Selector Bridging: locator dicts converted to Playwright selectors (id, testid, css, text via case-insensitive regex).
- DOM Resolver v1: verifies likely selectors via JS; prefers labelג†’input and attribute contains; enforces visible+enabled safety.
- Controls: radios/checkboxes prefer `page.check()` with click fallback for stability.
- Domain-Scoped Profiles: save/find with domain preference and JSONB containment ordering (Postgres), in-memory fallback.
- Healing KPIs: attempts/successes and profile hit/miss counters exposed to OTel/Prometheus.
- Runs API
  - `POST /api/runs` (create run; snapshot/live)
  - `GET /api/runs/{run_id}` (status + stats)
  - `GET /api/runs` (list with `mode`, `limit`, `offset`, `since`).
- Queue API
  - `POST /api/queue/runs`, `GET /api/queue/next`, `GET /api/queue/state`, `POST /api/queue/sample`.
- Profiles API
  - `GET /api/profiles` (best-effort), `POST /api/profiles/lookup` (supports `domain`).
- Portal Backend
  - `POST /runs` (proxy enqueue), `GET /runs/{jobId}` (status), `POST /tests/nl-run` (new NL flow), simple index page.

How To Use (Manual QA)
1) Live run from Portal NL API:
   - `POST http://localhost:8081/tests/nl-run`
   - Body:
     `{ "url": "about:blank", "stepsText": "click Login\ntype hello\npress Enter" }`
   - Then poll: `GET http://localhost:8081/runs/{jobId}`.
2) Optional LLM planner:
   - Set `KAIZEN_LLM_ENABLED=true`, `KAIZEN_PLANNER_PATH=llm` on engine-api/runner.
3) Allow real sites (optional):
   - `KAIZEN_ALLOWED_URL_SCHEMES=https://,http://,about:blank,data:`.
   - LLM (optional): ensure your local Ollama runs on the host and a model is pulled (e.g., `llama3.1`).
   - Compose defaults to LLM disabled; enable by flipping `KAIZEN_LLM_ENABLED=true`, `KAIZEN_PLANNER_PATH=llm` and setting `KAIZEN_OLLAMA_BASE_URL=http://host.docker.internal:11434`.
 3) Review artifacts for a run:
   - Engine API: `GET http://localhost:8080/api/runs/{run_id}/artifacts` lists items (e.g., `log`, `screenshot`).
   - Fetch a specific item: `GET http://localhost:8080/api/runs/{run_id}/artifacts/log` or `/screenshot`.

Developer Guide
- Tests: `python -m pytest -q` (or `make ci`).
- CLI: `python -m engine.api.cli snapshot-run <spec.json> --html <path|inline>` and `live-run`.
- Settings file: `engine/core/config/settings.py` (Pydantic; env prefix `KAIZEN_`).
- DI container: `engine/core/config/container.py`.
- Key modules:
  - Orchestrator: `engine/core/orchestrator/orchestrator.py`
  - Plan executor: `engine/core/orchestrator/plan_executor.py`
  - Healer: `engine/core/healing/selector_healer.py`
  - Resolver (DOM-aware v1): `engine/core/resolving/element_resolver.py`
    - JS-eval presence checks, label association, attribute contains (name/aria-label/placeholder/value), picks first visible+enabled. Healing remains backup.
  - Storage (Postgres): `engine/core/storage/postgres.py`
- Reporter: `engine/core/reporting/reporter.py`

Headed (visible) browser locally
- Recommended for manual debugging outside containers.
- Steps:
  - Create venv and install deps: `pip install -r requirements.txt && python -m playwright install chromium`
  - Set env to headed: on Windows PowerShell `setx KAIZEN_HEADFUL true` (or `$env:KAIZEN_HEADFUL="true"` for current session). On Unix: `export KAIZEN_HEADFUL=true`.
  - Optional slow motion: `KAIZEN_PW_SLOWMO=250` (ms).
  - Run a live spec locally: `python -m engine.api.cli live-run engine/tests/e2e_smoke/specs/live_spec.json --url https://httpbin.org/forms/post`.
  - The Chromium window opens visibly; close when done.

Note: running headed inside containers requires desktop/Display forwarding (X11/WSLg/VNC). Easiest is to run the engine locally as above.

Observability
- Collector config: `infra/otel-collector-config.yaml` (OTLP HTTP 4318, Prometheus exporter 9464).
- Prometheus scrape: `infra/prometheus.yml`.
- Grafana dashboard JSON: `infra/grafana/dashboards/kaizen.json`.
- If you see ׳’ג‚¬ֲno data׳’ג‚¬ֲ:
  - Recreate engine services so OTel deps install.
  - Trigger runs (use `/api/queue/sample`).
  - Healing KPIs appear only when healing is enabled and triggers.

What׳’ג‚¬ג„¢s Left / Next Missions
1) Resolver fidelity (high impact)
   - Replace stub `resolver.find()` with DOM-powered resolve. Improves click/type success and reduces reliance on healing.
2) Runs API + Portal (polish)
   - Add cursor-based pagination (`after=<run_id>`), optional DB-backed stats.
   - Portal ׳’ג‚¬ֲRuns׳’ג‚¬ֲ list page consuming `GET /api/runs`.
3) Profiles + Healer (polish)
   - Migrations (Alembic) and indexes; tie-breakers by specificity and hits finalized; domain normalization (registrable domain).
4) Prompt + Guardrails (P10)
   - Few-shots per tool; stricter JSON-only retry; input caps/rate-limit on `/api/plan/preview`.
5) Ops/Hardening
   - Secure admin endpoints behind dev flag; OTel sampler envs; bound metric label cardinality.

Troubleshooting
- Playwright headless live runs: ensure chromium is installed in runner container (compose handles this).
- OTel not exporting: check engine-api/runner logs for opentelemetry import errors; restart with `--force-recreate`.
- Grafana panels empty: trigger runs; healing panels require `KAIZEN_HEALER_ENABLED=true` and a scenario that triggers healing.
- Live run feels slow or hangs:
  - Lower timeouts: set `KAIZEN_PW_TIMEOUT_MS=5000`, `KAIZEN_PW_NAV_TIMEOUT_MS=10000`.
  - Wait strategy: try `KAIZEN_NAV_WAIT=networkidle` for heavy SPA pages.
  - Verify site loads: run headed (`KAIZEN_HEADFUL=true`) and watch the page.
  - Inspect per-run log at `/api/runs/{run_id}/artifacts/log` for timing and failed selectors.
- Resolver oddities: if an element repeatedly fails to resolve, fetch the per-run log via `GET /api/runs/{run_id}/artifacts` and share it; extend ranking/selector synthesis based on evidence.

Documentation
- Project Guide: `docs/PROJECT_GUIDE.md`
- Observability: `docs/observability.md`
- CI (Jenkins): `docs/CI_JENKINS.md`
- Security Policy: `docs/SECURITY.md`
- Architecture Decisions: `docs/ADRs/`
- Project Plan (live): `docs/KAIZEN_PLAN.md`

Artifacts Storage & Retention
- Default backend is filesystem (logs/ and snapshots/).
- Optional MinIO (S3-compatible) backend:
  - `KAIZEN_ARTIFACTS_BACKEND=minio`
  - `KAIZEN_MINIO_ENDPOINT`, `KAIZEN_MINIO_BUCKET`, `KAIZEN_MINIO_ACCESS_KEY`, `KAIZEN_MINIO_SECRET_KEY`, `KAIZEN_MINIO_SECURE=true|false`
- Retention (FS only):
  - `KAIZEN_ARTIFACTS_RETENTION_DAYS` and/or `KAIZEN_ARTIFACTS_RETENTION_MAX_BYTES`
  - Run `make artifacts-retain` (or `python scripts/artifacts_retention.py`)

License
- See LICENSE.

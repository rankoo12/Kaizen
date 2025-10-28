# OpenTelemetry Phase 0 (Bootstrap)

This repo now initializes OpenTelemetry in the Engine API and Runner to emit basic traces and metrics through an OTel Collector to Jaeger and a Prometheus endpoint.

## What’s included
- Tracing and metrics initialization in:
  - `engine/api/server.py` with `service.name=kaizen-engine-api` and FastAPI instrumentation.
  - `engine/runner/__main__.py` with `service.name=kaizen-engine-runner`.
- One span per run: `kaizen.run` with attributes `run_id` and `mode`.
- Metrics:
  - Counter `kaizen_runs_total{mode}`
  - Counter `kaizen_runs_failed_total{mode}`
  - Histogram `kaizen_run_duration_seconds{mode}`
  - Histogram `kaizen_step_duration_seconds{tool,ok,reason}`
  - Gauge `kaizen_queue_depth{state=queued|running}`
- Logs:
  - JSONL run logs under `logs/run-*.jsonl` include `trace_id` and `span_id` fields for correlation.
  - Collector `filelog` receiver ingests these files and exports to its own log sink (stdout) for quick validation.
- Docker Compose add-ons:
  - `otel-collector` listening on OTLP HTTP `:4318`
  - `jaeger` all-in-one with UI on `:16686`
  - Collector exposes Prometheus metrics on `:9464/metrics`

## How to run
1. Start the stack:
   - From `infra/`, run: `docker compose up --build`
2. Open Jaeger UI:
   - http://localhost:16686 (Search by service: `kaizen-engine-api` or `kaizen-engine-runner`)
3. Open Grafana:
   - http://localhost:3000 (admin/admin)
   - Prometheus datasource pre-provisioned; dashboard "Kaizen Observability" is loaded.
3. Trigger a run (examples):
   - POST a run to the Engine API: `POST http://localhost:8080/api/runs {"spec": {}}`
   - Or enqueue and let the runner pick it via the existing queue endpoints.
4. Verify traces:
   - In Jaeger, look for span names `kaizen.run` and check attributes `run_id` and `mode`.
5. Verify metrics:
   - Visit Collector metrics: http://localhost:9464/metrics
   - Look for `kaizen_runs_total`, `kaizen_runs_failed_total`, `kaizen_run_duration_seconds`, `kaizen_step_duration_seconds`, and `kaizen_queue_depth`.
6. Verify logs:
   - Trigger a sample run: `curl -X POST http://localhost:8080/api/queue/sample`
   - Check collector logs for ingested entries (look for `filelog` lines): `docker compose logs -f otel-collector`
   - Open a `run-*.jsonl` and confirm it contains `trace_id`/`span_id`; the corresponding trace in Jaeger shares the same IDs.

## Grafana Panels (starter)
- Run Rate by Mode (5m): `sum by (mode) (rate(kaizen_runs_total[5m]))`
- Failed Runs (1h): `sum(increase(kaizen_runs_failed_total[1h]))`
- P95 Step Duration (5m): `histogram_quantile(0.95, sum by (le, tool) (rate(kaizen_step_duration_seconds_bucket[5m])))`
- Queue Depth: `kaizen_queue_depth{state="queued"}` and `{state="running"}`

## Environment variables
- `OTEL_EXPORTER_OTLP_ENDPOINT` (default: `http://otel-collector:4318` inside compose)
  - Both Engine API and Runner set this in `infra/docker-compose.yml`.

## Notes
- Existing APIs, reporter, metrics, and artifacts remain unchanged.
- If OpenTelemetry packages are not present (e.g., in local tests), the code degrades to a no-op without failing.
- Phase 1 will add step spans and more attributes through the reporter hooks.

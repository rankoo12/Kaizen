# 0005: Portal Thin UI (Phase 2)

Status: Accepted

Context

- We need a very thin Portal to trigger suites and observe runs.
- Keep the Engine deterministic and re‑use the existing orchestrator+reporter.
- Avoid WebSockets for now; use simple polling.

Decision

- Add a lightweight Portal backend that proxies to Engine API:
  - Create/Store suite specs via `POST /api/suites`.
  - Trigger execution via a queue using `POST /api/queue/runs`.
  - Observe job state via `GET /api/queue/state` and run status via `GET /api/runs/{id}`.
- Provide one minimal HTML page (served by Portal) that:
  - Accepts a suite spec JSON.
  - Enqueues a run job.
  - Polls every 1–2 seconds for job state and run stats (reasons/heal/planner/by_tool).
- No websockets; no persistence beyond in‑memory for now.

Consequences

- The runner container can scale independently and respect `RUNNER_CONCURRENCY`.
- Users get immediate visibility into queued vs running and final stats via polling.
- Later we can swap the in‑memory queue with a durable one without changing the Portal API.

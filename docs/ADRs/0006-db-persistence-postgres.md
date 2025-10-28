# 0006: Postgres-First Persistence (Phase A)

Status: Accepted

Context

- We need durable, query-friendly storage for runs, steps, suites, queue, and (soon) learned selectors.
- We want strong analytics (e.g., “top failing steps per suite over time”), ACID transactions, and simple ops.
- Artifacts (logs JSONL, snapshots HTML/JSON/JSONL) can be large/append-heavy — better kept on disk or object storage.

Decision

- Use PostgreSQL as the primary store for core entities. Use JSONB for flexible fields (stats, args, signatures, payloads).
- Keep raw artifacts on disk (or S3/MinIO later). Persist pointers + hashes in DB, serve via Engine API.
- Provide a storage abstraction (IStorage) and implement a PostgresStorage backend. Keep in-memory as fallback.

Configuration

- KAIZEN_PG_DSN: e.g., `postgresql+psycopg://kaizen:kaizen@postgres:5432/kaizen`
- KAIZEN_STORAGE_BACKEND: `postgres` | `in_memory` (default can auto-pick when DSN present)

Schema (tables, key columns)

- runs
  - id PK, run_id UNIQUE
  - mode TEXT, website TEXT NULL, status TEXT
  - started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ NULL
  - stats JSONB, artifacts JSONB, meta JSONB
  - Indexes: unique(run_id), status, started_at

- steps
  - id PK, run_id TEXT FK (logical), index INT
  - ts TIMESTAMPTZ, tool TEXT, args_redacted JSONB, ok BOOL, reason TEXT, signature JSONB
  - Indexes: unique(run_id, index), run_id

- suites
  - id PK, suite_id UNIQUE, spec JSONB, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
  - Indexes: unique(suite_id)

- queue
  - id PK, job_id UNIQUE, payload JSONB, status TEXT, run_id TEXT NULL
  - created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
  - Indexes: unique(job_id), status, created_at
  - Atomic claim: `FOR UPDATE SKIP LOCKED` to fetch+transition a queued job to running.

- selectors (learning)
  - id PK, website TEXT, key TEXT, signature JSONB, locator JSONB, confidence FLOAT, sources JSONB, last_seen TIMESTAMPTZ
  - Indexes: unique(website, key), website

Artifacts Strategy

- Keep raw files on filesystem volumes (current default) or object storage later.
- Store pointers in runs.artifacts (e.g., `{"log_path": "logs/run-…jsonl", "snapshot_dir": "snapshots/…"}`) and optionally a secondary artifact index table.
- Serve via API with allow-list + scrubbing.

PII / Security

- Store step args as `args_redacted` (scrub secrets/free text before insert when applicable).
- No secrets in artifacts; scrub on serve (emails, long digit sequences) — keep extensible.
- DB credentials via environment; least-privilege role; TLS configurable later.

Scale & Concurrency

- Multi-instance Engine API / runner supported:
  - Queue claim uses `FOR UPDATE SKIP LOCKED` to avoid thundering herd.
  - `runs.start` insert/update within a transaction; `runs.finish` idempotent by run_id.
  - Steps enforced by unique(run_id, index) to prevent duplicate appends.

Operational Notes

- Migrations: bootstrap `CREATE TABLE IF NOT EXISTS` + indexes at startup.
- Backups: use standard Postgres tooling; artifacts backed separately (or object storage lifecycle).
- Observability: metrics/rollups remain in memory for live dashboards; authoritative status/stats in DB.

Rollout Plan

1) Implement PostgresStorage with psycopg and bootstrap DDL.
2) Wire DI to choose Postgres when KAIZEN_PG_DSN present; otherwise in-memory.
3) Update Engine API (suites, queue, runs GET) to use storage.
4) Add integration tests (opt-in via KAIZEN_PG_TEST env).
5) Later: add selectors learning + lookup using the selectors table.

Alternatives Considered

- Mongo-only: faster early iteration, but weaker analytics/joins and more work for cross-entity queries.
- Hybrid (Mongo selectors + Postgres core): best fit per workload, but higher ops complexity — defer until needed.

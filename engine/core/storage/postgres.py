from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


DDL = {
    "runs": """
    CREATE TABLE IF NOT EXISTS runs (
        id SERIAL PRIMARY KEY,
        run_id TEXT UNIQUE NOT NULL,
        mode TEXT NULL,
        website TEXT NULL,
        status TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        finished_at TIMESTAMPTZ NULL,
        stats JSONB NOT NULL DEFAULT '{}'::jsonb,
        artifacts JSONB NOT NULL DEFAULT '{}'::jsonb,
        meta JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS runs_status_idx ON runs(status);
    CREATE INDEX IF NOT EXISTS runs_started_idx ON runs(started_at);
    """,
    "steps": """
    CREATE TABLE IF NOT EXISTS steps (
        id SERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        idx INT NOT NULL,
        ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        tool TEXT NULL,
        args_redacted JSONB NOT NULL DEFAULT '{}'::jsonb,
        ok BOOLEAN NULL,
        reason TEXT NULL,
        signature JSONB NOT NULL DEFAULT '{}'::jsonb,
        UNIQUE(run_id, idx)
    );
    CREATE INDEX IF NOT EXISTS steps_run_idx ON steps(run_id);
    """,
    "suites": """
    CREATE TABLE IF NOT EXISTS suites (
        id SERIAL PRIMARY KEY,
        suite_id TEXT UNIQUE NOT NULL,
        spec JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "queue": """
    CREATE TABLE IF NOT EXISTS queue (
        id SERIAL PRIMARY KEY,
        job_id TEXT UNIQUE NOT NULL,
        payload JSONB NOT NULL,
        status TEXT NOT NULL,
        run_id TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS queue_status_idx ON queue(status);
    CREATE INDEX IF NOT EXISTS queue_created_idx ON queue(created_at);
    """,
    "selectors": """
    CREATE TABLE IF NOT EXISTS selectors (
        id SERIAL PRIMARY KEY,
        website TEXT NOT NULL,
        key TEXT NOT NULL,
        signature JSONB NOT NULL DEFAULT '{}'::jsonb,
        locator JSONB NOT NULL DEFAULT '{}'::jsonb,
        confidence DOUBLE PRECISION NULL,
        sources JSONB NOT NULL DEFAULT '[]'::jsonb,
        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(website, key)
    );
    CREATE INDEX IF NOT EXISTS selectors_site_idx ON selectors(website);
    """,
}


class PostgresStorage:
    """Postgres-backed storage using psycopg.

    Keeps artifacts on disk; stores pointers in runs.artifacts.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._bootstrap()

    def _bootstrap(self) -> None:
        with self._conn.cursor() as cur:
            for ddl in DDL.values():
                cur.execute(ddl)

    # --------------- Runs ---------------
    def start_run(self, test_id: str, website: Optional[str] = None) -> str:
        base = (test_id or "run").replace(" ", "-")
        run_id = f"run-{base}"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs(run_id, website, status, started_at)
                VALUES (%s, %s, 'running', NOW())
                ON CONFLICT (run_id) DO UPDATE SET started_at = EXCLUDED.started_at
                RETURNING run_id
                """,
                (run_id, website),
            )
            row = cur.fetchone()
            return row[0]

    def finish_run(self, run_id: str, stats: Optional[dict] = None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs(run_id, status, started_at)
                VALUES (%s, 'finished', NOW())
                ON CONFLICT (run_id)
                DO UPDATE SET status='finished', finished_at=NOW(), stats=COALESCE(%s, '{}'::jsonb)
                """,
                (run_id, psycopg.adapters.Json(stats or {})),
            )

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT run_id, status, mode, website, started_at, finished_at, stats FROM runs WHERE run_id=%s", (run_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # --------------- Steps ---------------
    def record_step(self, step: Dict[str, Any]) -> None:
        run_id = str(step.get("run_id"))
        idx = int(step.get("index") or step.get("step_index") or 0)
        tool = step.get("tool")
        ok = bool(step.get("ok")) if "ok" in step else None
        reason = step.get("reason")
        signature = step.get("signature") or {}
        args_redacted = step.get("args_redacted") or {}
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO steps(run_id, idx, tool, ok, reason, signature, args_redacted)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, idx)
                DO UPDATE SET tool=EXCLUDED.tool, ok=EXCLUDED.ok, reason=EXCLUDED.reason,
                              signature=EXCLUDED.signature, args_redacted=EXCLUDED.args_redacted
                """,
                (
                    run_id,
                    idx,
                    tool,
                    ok,
                    reason,
                    psycopg.adapters.Json(signature),
                    psycopg.adapters.Json(args_redacted),
                ),
            )

    # --------------- Suites ---------------
    def save_suite(self, suite_id: str, spec: Dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO suites(suite_id, spec)
                VALUES (%s, %s)
                ON CONFLICT (suite_id)
                DO UPDATE SET spec=EXCLUDED.spec, updated_at=NOW()
                """,
                (suite_id, psycopg.adapters.Json(spec)),
            )

    def get_suite(self, suite_id: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT suite_id, spec FROM suites WHERE suite_id=%s", (suite_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # --------------- Queue ---------------
    def enqueue(self, payload: Dict[str, Any]) -> str:
        import time

        job_id = f"job-{int(time.time()*1000)}"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO queue(job_id, payload, status, created_at, updated_at)
                VALUES (%s, %s, 'queued', NOW(), NOW())
                """,
                (job_id, psycopg.adapters.Json(payload or {})),
            )
        return job_id

    def next_job(self) -> Optional[Dict[str, Any]]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                WITH c AS (
                  SELECT id FROM queue WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE queue SET status='running', updated_at=NOW()
                WHERE id IN (SELECT id FROM c)
                RETURNING job_id, payload
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            payload = row["payload"] or {}
            return {"job_id": row["job_id"], **payload}

    def mark_running(self, job_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                UPDATE queue SET status='running', run_id=COALESCE(%s, run_id), updated_at=NOW()
                WHERE job_id=%s
                RETURNING job_id, run_id
                """,
                (run_id, job_id),
            )
            row = cur.fetchone()
            return dict(row) if row else {"job_id": job_id, "run_id": run_id}

    def complete(self, job_id: str, run_id: Optional[str] = None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE queue SET status='complete', run_id=COALESCE(%s, run_id), updated_at=NOW()
                WHERE job_id=%s
                """,
                (run_id, job_id),
            )

    def state(self) -> Dict[str, Any]:
        with self._conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT job_id FROM queue WHERE status='queued' ORDER BY created_at")
            queued = [{"job_id": r["job_id"]} for r in cur.fetchall()]
            cur.execute("SELECT job_id, run_id FROM queue WHERE status='running'")
            running = [{"job_id": r["job_id"], "run_id": r["run_id"]} for r in cur.fetchall()]
        return {"queued": queued, "running": running}

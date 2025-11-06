from __future__ import annotations

import json
import time
from typing import Any, Optional

import psycopg


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ensure_schema()

    def _conn(self):
        return psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self) -> None:
        ddl = (
            """
            -- runs table
            CREATE TABLE IF NOT EXISTS runs (
              id SERIAL PRIMARY KEY,
              run_id TEXT UNIQUE,
              test_id TEXT,
              website TEXT NULL,
              started_at TIMESTAMPTZ DEFAULT NOW(),
              finished_at TIMESTAMPTZ,
              stats JSONB
            );
            CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);

            -- steps table (minimal for future expansion)
            CREATE TABLE IF NOT EXISTS steps (
              id SERIAL PRIMARY KEY,
              run_id TEXT,
              idx INT,
              ts TIMESTAMPTZ DEFAULT NOW(),
              tool TEXT,
              args_redacted JSONB,
              ok BOOL,
              reason TEXT,
              signature JSONB
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_run_idx ON steps(run_id, idx);

            -- suites table
            CREATE TABLE IF NOT EXISTS suites (
              id SERIAL PRIMARY KEY,
              suite_id TEXT UNIQUE,
              spec JSONB,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ DEFAULT NOW()
            );

            -- durable queue
            CREATE TABLE IF NOT EXISTS queue (
              id SERIAL PRIMARY KEY,
              job_id TEXT UNIQUE,
              payload JSONB,
              status TEXT,
              run_id TEXT NULL,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_queue_status_created ON queue(status, created_at);

            -- locator profiles (learning)
            CREATE TABLE IF NOT EXISTS locator_profiles (
              id SERIAL PRIMARY KEY,
              domain TEXT,
              tool TEXT,
              target_signature JSONB,
              selector JSONB,
              hits INT DEFAULT 0,
              last_seen TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_profiles_domain_tool ON locator_profiles(domain, tool);
            CREATE INDEX IF NOT EXISTS idx_profiles_sig ON locator_profiles USING GIN (target_signature);

            -- multi-tenant basics
            CREATE TABLE IF NOT EXISTS tenants (
              id SERIAL PRIMARY KEY,
              tenant_id TEXT UNIQUE,
              name TEXT
            );
            CREATE TABLE IF NOT EXISTS api_keys (
              id SERIAL PRIMARY KEY,
              tenant_id TEXT REFERENCES tenants(tenant_id) ON DELETE CASCADE,
              api_key TEXT UNIQUE,
              api_key_hash TEXT,
              created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(api_key_hash);
            """
        )
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
                # Best-effort additive schema updates for multitenancy
                try:
                    cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS tenant_id TEXT")
                except Exception:
                    pass
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_tenant ON runs(tenant_id)")
                except Exception:
                    pass

    # ---- Run lifecycle (compat with orchestrator) ----
    def start_run(self, test_id: str, website: str | None = None) -> str:
        run_id = f"run-{int(time.time())}-{test_id}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                if website:
                    cur.execute(
                        "INSERT INTO runs(run_id, test_id, website) VALUES (%s, %s, %s) ON CONFLICT (run_id) DO NOTHING",
                        (run_id, test_id, website),
                    )
                else:
                    cur.execute(
                        "INSERT INTO runs(run_id, test_id) VALUES (%s, %s) ON CONFLICT (run_id) DO NOTHING",
                        (run_id, test_id),
                    )
        return run_id

    def record_step(self, step: dict) -> None:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO steps(run_id, idx, ts, tool, args_redacted, ok, reason, signature)
                        VALUES (%s, %s, NOW(), %s, %s::jsonb, %s, %s, %s::jsonb)
                        ON CONFLICT (run_id, idx) DO NOTHING
                        """,
                        (
                            step.get("run_id"),
                            int(step.get("index", 0) or 0),
                            step.get("tool"),
                            json.dumps(step.get("args_redacted", {})),
                            bool(step.get("ok", False)),
                            step.get("reason"),
                            json.dumps(step.get("signature", {})),
                        ),
                    )
        except Exception:
            return None

    def finish_run(self, run_id: str, stats: dict | None = None) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                if stats is None:
                    cur.execute(
                        "UPDATE runs SET finished_at=NOW() WHERE run_id=%s",
                        (run_id,),
                    )
                else:
                    cur.execute(
                        "UPDATE runs SET finished_at=NOW(), stats=%s::jsonb WHERE run_id=%s",
                        (json.dumps(stats), run_id),
                    )

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_id, website, extract(epoch from started_at), extract(epoch from finished_at), stats, tenant_id FROM runs WHERE run_id=%s",
                    (run_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                status = "finished" if row[3] is not None else "running"
                return {
                    "run_id": row[0],
                    "website": row[1],
                    "started": float(row[2] or 0),
                    "finished": float(row[3]) if row[3] is not None else None,
                    "status": status,
                    "stats": row[4] if isinstance(row[4], dict) else (json.loads(row[4]) if row[4] else {}),
                    "tenant_id": row[5],
                }

    # ---- Suites ----
    def save_suite(self, suite_id: str, spec: dict) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO suites(suite_id, spec) VALUES (%s, %s::jsonb)
                    ON CONFLICT (suite_id) DO UPDATE SET spec=EXCLUDED.spec, updated_at=NOW()
                    """,
                    (suite_id, json.dumps(spec)),
                )

    def get_suite(self, suite_id: str) -> Optional[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT suite_id, spec FROM suites WHERE suite_id=%s", (suite_id,))
                row = cur.fetchone()
                if not row:
                    return None
                spec = row[1] if isinstance(row[1], dict) else (json.loads(row[1]) if row[1] else {})
                return {"suite_id": row[0], "spec": spec}

    # ---- Durable Queue ----
    def enqueue(self, payload: dict) -> str:
        job_id = f"job-{int(time.time()*1000)}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO queue(job_id, payload, status) VALUES (%s, %s::jsonb, 'queued')",
                    (job_id, json.dumps(payload or {})),
                )
        return job_id

    def next_job(self) -> Optional[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Requeue stale running jobs based on lease timeout (seconds)
                try:
                    import os as _os
                    lease = int(_os.environ.get("KAIZEN_QUEUE_LEASE_SEC", "300") or 300)
                except Exception:
                    lease = 300
                try:
                    cur.execute(
                        "UPDATE queue SET status='queued', updated_at=NOW() "
                        "WHERE status='running' AND updated_at < NOW() - (%s || ' seconds')::interval",
                        (str(int(lease)),),
                    )
                except Exception:
                    pass
                cur.execute(
                    """
                    SELECT id, job_id, payload FROM queue
                    WHERE status='queued'
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if not row:
                    return None
                qid, job_id, payload = row
                cur.execute(
                    "UPDATE queue SET status='running', updated_at=NOW() WHERE id=%s",
                    (qid,),
                )
                try:
                    obj = payload if isinstance(payload, dict) else json.loads(payload)
                except Exception:
                    obj = {}
                obj["job_id"] = job_id
                return obj

    def mark_running(self, job_id: str, run_id: str | None = None) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE queue SET status='running', run_id=%s, updated_at=NOW() WHERE job_id=%s",
                    (run_id, job_id),
                )
                # Propagate tenant_id from queue payload to runs row when available
                try:
                    cur.execute("SELECT payload->>'tenant_id' FROM queue WHERE job_id=%s", (job_id,))
                    row = cur.fetchone()
                    if row and row[0] and run_id:
                        cur.execute("UPDATE runs SET tenant_id=%s WHERE run_id=%s", (row[0], run_id))
                except Exception:
                    pass

    def complete(self, job_id: str, run_id: str | None = None) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE queue SET status='completed', run_id=%s, updated_at=NOW() WHERE job_id=%s",
                    (run_id, job_id),
                )

    def state(self, tenant: str | None = None) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                if tenant:
                    cur.execute(
                        "SELECT job_id FROM queue WHERE status='queued' AND (payload->>'tenant_id') IS NOT DISTINCT FROM %s ORDER BY created_at LIMIT 200",
                        (tenant,),
                    )
                else:
                    cur.execute(
                        "SELECT job_id FROM queue WHERE status='queued' ORDER BY created_at LIMIT 200"
                    )
                queued = [{"job_id": r[0]} for r in (cur.fetchall() or [])]
                if tenant:
                    cur.execute(
                        "SELECT job_id, run_id FROM queue WHERE status='running' AND (payload->>'tenant_id') IS NOT DISTINCT FROM %s ORDER BY updated_at DESC LIMIT 200",
                        (tenant,),
                    )
                else:
                    cur.execute(
                        "SELECT job_id, run_id FROM queue WHERE status='running' ORDER BY updated_at DESC LIMIT 200"
                    )
                running = [
                    {"job_id": r[0], "run_id": r[1]} for r in (cur.fetchall() or [])
                ]
                if tenant:
                    cur.execute(
                        "SELECT job_id, run_id, extract(epoch from updated_at) FROM queue WHERE status='completed' AND (payload->>'tenant_id') IS NOT DISTINCT FROM %s ORDER BY updated_at DESC LIMIT 50",
                        (tenant,),
                    )
                else:
                    cur.execute(
                        "SELECT job_id, run_id, extract(epoch from updated_at) FROM queue WHERE status='completed' ORDER BY updated_at DESC LIMIT 50"
                    )
                completed = [
                    {"job_id": r[0], "run_id": r[1], "ts": float(r[2] or 0)}
                    for r in (cur.fetchall() or [])
                ]
        return {"queued": queued, "running": running, "completed": completed}

    # ---- Locator Profiles ----
    def save_locator_profile(self, *, domain: Optional[str], tool: str, target_signature: dict, selector: dict) -> None:
        sel_json = json.dumps({"type": selector.get("type"), "value": selector.get("value")})
        sig_json = json.dumps(target_signature or {})
        with self._conn() as conn:
            with conn.cursor() as cur:
                # 1) Try to update existing by (domain, tool, selector)
                cur.execute(
                    """
                    UPDATE locator_profiles
                    SET hits = hits + 1, last_seen = NOW()
                    WHERE (domain IS NOT DISTINCT FROM %s) AND tool=%s AND selector=%s::jsonb
                    """,
                    (domain, tool, sel_json),
                )
                if cur.rowcount and cur.rowcount > 0:
                    return
                # 2) Insert new
                cur.execute(
                    """
                    INSERT INTO locator_profiles(domain, tool, target_signature, selector, hits)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb, 1)
                    """,
                    (domain, tool, sig_json, sel_json),
                )

    def find_locator_profile(self, *, domain: Optional[str], tool: str, target_signature: dict) -> Optional[dict]:
        # Prefer domain-scoped exact/signature matches; fallback to global; rank by specificity and usage
        with self._conn() as conn:
            with conn.cursor() as cur:
                sig = json.dumps(target_signature or {})
                if target_signature:
                    cur.execute(
                        """
                        SELECT selector FROM locator_profiles
                        WHERE tool=%s AND ((domain IS NOT DISTINCT FROM %s) OR domain IS NULL)
                          AND target_signature @> %s::jsonb
                        ORDER BY (CASE WHEN domain IS NOT DISTINCT FROM %s THEN 1 ELSE 0 END) DESC,
                                 (SELECT COUNT(*) FROM jsonb_object_keys(target_signature)) DESC,
                                 hits DESC,
                                 last_seen DESC
                        LIMIT 1
                        """,
                        (tool, domain, sig, domain),
                    )
                else:
                    cur.execute(
                        """
                        SELECT selector FROM locator_profiles
                        WHERE tool=%s AND ((domain IS NOT DISTINCT FROM %s) OR domain IS NULL)
                        ORDER BY (CASE WHEN domain IS NOT DISTINCT FROM %s THEN 1 ELSE 0 END) DESC,
                                 hits DESC, last_seen DESC
                        LIMIT 1
                        """,
                        (tool, domain, domain),
                    )
                row = cur.fetchone()
                if row and row[0]:
                    try:
                        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    except Exception:
                        return None
        return None

    # ---- Tenants / API Keys ----
    def create_tenant(self, tenant_id: str, name: str | None = None) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tenants(tenant_id, name) VALUES (%s, %s) ON CONFLICT (tenant_id) DO NOTHING",
                    (tenant_id, name),
                )

    def create_api_key(self, tenant_id: str, api_key: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Store only a hash of the API key. Fallback to plaintext insert only if hashing fails.
                try:
                    import hashlib as _hash
                    api_hash = _hash.sha256(api_key.encode("utf-8")).hexdigest()
                    cur.execute(
                        "INSERT INTO api_keys(tenant_id, api_key_hash) VALUES (%s, %s) ON CONFLICT (api_key_hash) DO NOTHING",
                        (tenant_id, api_hash),
                    )
                except Exception:
                    cur.execute(
                        "INSERT INTO api_keys(tenant_id, api_key) VALUES (%s, %s) ON CONFLICT (api_key) DO NOTHING",
                        (tenant_id, api_key),
                    )

    def resolve_tenant(self, api_key: str | None) -> str | None:
        if not api_key:
            return None
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Prefer hash-based lookup; fallback to plaintext if unavailable
                try:
                    import hashlib as _hash

                    api_hash = _hash.sha256(api_key.encode("utf-8")).hexdigest()
                    cur.execute("SELECT tenant_id FROM api_keys WHERE api_key_hash=%s", (api_hash,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
                except Exception:
                    pass
                try:
                    cur.execute("SELECT tenant_id FROM api_keys WHERE api_key=%s", (api_key,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
                except Exception:
                    pass
                return None

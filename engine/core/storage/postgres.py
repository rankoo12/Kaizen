from __future__ import annotations

import json
import time
from typing import Any, Optional

import psycopg
from engine.core.config.settings import settings as _settings


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
              signature JSONB,
              tenant_id TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_run_idx ON steps(run_id, idx);
            CREATE INDEX IF NOT EXISTS idx_steps_tenant ON steps(tenant_id);

            -- per-action human/ML annotations (for PageBrain training)
            CREATE TABLE IF NOT EXISTS run_action_annotations (
              id SERIAL PRIMARY KEY,
              run_id TEXT NOT NULL,
              action_index INT NOT NULL,
              test_id TEXT NULL,
              step_id TEXT NULL,
              label TEXT NOT NULL,
              source TEXT NOT NULL,
              notes TEXT NULL,
              user_id TEXT NULL,
              created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_run_action_annotations_uniq
              ON run_action_annotations(run_id, action_index, source);
            CREATE INDEX IF NOT EXISTS idx_run_action_annotations_run
              ON run_action_annotations(run_id);

            -- suites table
            CREATE TABLE IF NOT EXISTS suites (
              id SERIAL PRIMARY KEY,
              suite_id TEXT UNIQUE,
              spec JSONB,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ DEFAULT NOW(),
              tenant_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_suites_tenant ON suites(tenant_id);

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
                try:
                    cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS fields JSONB")
                except Exception:
                    pass
                try:
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_runs_suite_run_id ON runs((fields->>'suite_run_id'))"
                    )
                except Exception:
                    pass
                # Best-effort additive columns for annotations metadata
                try:
                    cur.execute("ALTER TABLE run_action_annotations ADD COLUMN IF NOT EXISTS selector JSONB")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE run_action_annotations ADD COLUMN IF NOT EXISTS domain TEXT")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE run_action_annotations ADD COLUMN IF NOT EXISTS tool TEXT")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE run_action_annotations ADD COLUMN IF NOT EXISTS target_signature JSONB")
                except Exception:
                    pass
                try:
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_run_action_annotations_selector "
                        "ON run_action_annotations( (selector->>'value') )"
                    )
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE steps ADD COLUMN IF NOT EXISTS tenant_id TEXT")
                except Exception:
                    pass
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_steps_tenant ON steps(tenant_id)")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE suites ADD COLUMN IF NOT EXISTS tenant_id TEXT")
                except Exception:
                    pass
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_suites_tenant ON suites(tenant_id)")
                except Exception:
                    pass
                # Retrieval embeddings (JSONB vector + optional pgvector column)
                try:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS retrieval_embeddings (
                          id SERIAL PRIMARY KEY,
                          tenant_id TEXT,
                          domain TEXT,
                          tool TEXT,
                          target_signature JSONB,
                          selector JSONB,
                          vector JSONB,
                          created_at TIMESTAMPTZ DEFAULT NOW()
                        );
                        """
                    )
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_tenant ON retrieval_embeddings(tenant_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_domain_tool ON retrieval_embeddings(domain, tool)")
                except Exception:
                    pass
                # Best-effort pgvector extension + column and ANN index
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                except Exception:
                    # Extension not available; JSONB fallback remains
                    pass
                try:
                    cur.execute("ALTER TABLE retrieval_embeddings ADD COLUMN IF NOT EXISTS vec vector")
                except Exception:
                    pass
                try:
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_retrieval_vec ON retrieval_embeddings USING ivfflat (vec vector_cosine_ops)"
                    )
                except Exception:
                    # ivfflat or vector_cosine_ops may be unavailable; ignore
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
                    # Resolve tenant_id from the parent run if available
                    tenant_id = None
                    try:
                        cur.execute("SELECT tenant_id FROM runs WHERE run_id=%s", (step.get("run_id"),))
                        row = cur.fetchone()
                        if row:
                            tenant_id = row[0]
                    except Exception:
                        tenant_id = None
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
                    # Backfill tenant_id if available
                    try:
                        if tenant_id is not None:
                            cur.execute(
                                "UPDATE steps SET tenant_id=%s WHERE run_id=%s AND idx=%s",
                                (
                                    tenant_id,
                                    step.get("run_id"),
                                    int(step.get("index", 0) or 0),
                                ),
                            )
                    except Exception:
                        pass
        except Exception:
            return None

    def save_run_action_annotation(
        self,
        *,
        run_id: str,
        action_index: int,
        label: str,
        source: str,
        notes: str | None = None,
        user_id: str | None = None,
        selector: dict | None = None,
        domain: str | None = None,
        tool: str | None = None,
        target_signature: dict | None = None,
    ) -> dict | None:
        """Insert or update a per-action annotation for a run (PageBrain labels)."""
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    # Try to resolve test_id from the parent run when available
                    test_id: str | None = None
                    resolved_domain: str | None = domain
                    try:
                        cur.execute(
                            "SELECT test_id, website FROM runs WHERE run_id=%s", (run_id,)
                        )
                        row = cur.fetchone()
                        if row:
                            test_id = row[0]
                            if resolved_domain is None and row[1]:
                                # Best-effort extract host from website URL
                                try:
                                    from urllib.parse import urlparse as _urlparse

                                    parsed = _urlparse(str(row[1]))
                                    resolved_domain = parsed.hostname or str(row[1])
                                except Exception:
                                    resolved_domain = str(row[1])
                    except Exception:
                        test_id = None
                        resolved_domain = domain
                    sel_json = json.dumps(selector) if selector is not None else None
                    sig_json = json.dumps(target_signature) if target_signature is not None else None
                    cur.execute(
                        """
                        INSERT INTO run_action_annotations(run_id, action_index, test_id, label, source, notes, user_id, selector, domain, tool, target_signature)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                        ON CONFLICT (run_id, action_index, source)
                        DO UPDATE SET
                          label=EXCLUDED.label,
                          notes=EXCLUDED.notes,
                          user_id=EXCLUDED.user_id,
                          selector=COALESCE(EXCLUDED.selector, run_action_annotations.selector),
                          domain=COALESCE(EXCLUDED.domain, run_action_annotations.domain),
                          tool=COALESCE(EXCLUDED.tool, run_action_annotations.tool),
                          target_signature=COALESCE(EXCLUDED.target_signature, run_action_annotations.target_signature)
                        RETURNING run_id, action_index, test_id, step_id, label, source, notes, user_id, created_at, selector, domain, tool, target_signature
                        """,
                        (
                            str(run_id),
                            int(action_index),
                            test_id,
                            str(label),
                            str(source),
                            notes,
                            user_id,
                            sel_json,
                            resolved_domain,
                            tool,
                            sig_json,
                        ),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "run_id": row[0],
                        "action_index": int(row[1]) if row[1] is not None else None,
                        "test_id": row[2],
                        "step_id": row[3],
                        "label": row[4],
                        "source": row[5],
                        "notes": row[6],
                        "user_id": row[7],
                        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else row[8],
                        "selector": row[9] if isinstance(row[9], dict) else (json.loads(row[9]) if row[9] else None),
                        "domain": row[10],
                        "tool": row[11],
                        "target_signature": row[12] if isinstance(row[12], dict) else (json.loads(row[12]) if row[12] else None),
                    }
        except Exception:
            return None

    def get_run_action_annotations(self, run_id: str) -> list[dict]:
        """Return all annotations for a given run_id, ordered by action_index then created_at."""
        out: list[dict] = []
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT run_id, action_index, test_id, step_id, label, source, notes, user_id, created_at, selector, domain, tool, target_signature
                        FROM run_action_annotations
                        WHERE run_id=%s
                        ORDER BY action_index ASC, created_at ASC
                        """,
                        (str(run_id),),
                    )
                    rows = cur.fetchall() or []
                    for row in rows:
                        out.append(
                            {
                                "run_id": row[0],
                                "action_index": int(row[1]) if row[1] is not None else None,
                                "test_id": row[2],
                                "step_id": row[3],
                                "label": row[4],
                                "source": row[5],
                                "notes": row[6],
                                "user_id": row[7],
                                "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else row[8],
                                "selector": row[9] if isinstance(row[9], dict) else (json.loads(row[9]) if row[9] else None),
                                "domain": row[10],
                                "tool": row[11],
                                "target_signature": row[12] if isinstance(row[12], dict) else (json.loads(row[12]) if row[12] else None),
                            }
                        )
        except Exception:
            return []
        return out

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
                    """
                    SELECT run_id, test_id, website,
                           extract(epoch from started_at),
                           extract(epoch from finished_at),
                           stats, tenant_id, fields
                    FROM runs
                    WHERE run_id=%s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                status = "finished" if row[4] is not None else "running"
                return {
                    "run_id": row[0],
                    "test_id": row[1],
                    "website": row[2],
                    "started": float(row[3] or 0),
                    "finished": float(row[4]) if row[4] is not None else None,
                    "status": status,
                    "stats": row[5] if isinstance(row[5], dict) else (json.loads(row[5]) if row[5] else {}),
                    "tenant_id": row[6],
                    "fields": row[7] if isinstance(row[7], dict) else (json.loads(row[7]) if row[7] else {}),
                }

    def get_selector_feedback_for_test(self, test_id: str) -> dict:
        """Aggregate human annotation feedback per selector for a given test_id.

        Returns a mapping of "type|value" -> {"passed": int, "failed": int, "total": int}.
        """
        feedback: dict[str, dict[str, int]] = {}
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT selector, label, COUNT(*) AS c
                        FROM run_action_annotations
                        WHERE test_id=%s AND selector IS NOT NULL
                        GROUP BY selector, label
                        """,
                        (str(test_id),),
                    )
                    rows = cur.fetchall() or []
                    for sel_raw, label, count in rows:
                        if sel_raw is None:
                            continue
                        try:
                            sel_obj = sel_raw if isinstance(sel_raw, dict) else json.loads(sel_raw)
                        except Exception:
                            continue
                        if not isinstance(sel_obj, dict):
                            continue
                        sel_type = sel_obj.get("type")
                        sel_value = sel_obj.get("value")
                        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
                            continue
                        key = f"{sel_type}|{sel_value}"
                        row_fb = feedback.setdefault(key, {"passed": 0, "failed": 0, "total": 0})
                        n = int(count or 0)
                        row_fb["total"] += n
                        lab = (str(label or "")).lower()
                        if lab == "passed":
                            row_fb["passed"] += n
                        elif lab == "failed":
                            row_fb["failed"] += n
        except Exception:
            return {}
        return feedback

    def get_preferred_selectors_for_test(self, test_id: str) -> dict:
        """Return best-known selectors per action_index for a given test.

        Shape:
            {
              0: {"type": "css", "value": "input[name=\"q\"]"},
              1: {"type": "css", "value": "button[aria-label=\"Search\"]"},
              ...
            }

        We pick, per action_index, the selector with:
        - passed >= 1 and passed >= failed, and
        - highest (passed - failed, passed).
        """
        out: dict[int, dict] = {}
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT action_index,
                               selector,
                               label,
                               target_signature,
                               created_at
                        FROM run_action_annotations
                        WHERE test_id=%s
                          AND action_index IS NOT NULL
                          AND selector IS NOT NULL
                        ORDER BY created_at DESC
                        """,
                        (str(test_id),),
                    )
                    rows = cur.fetchall() or []
                    stats: dict[tuple[int, str, str], dict[str, int]] = {}
                    sigs: dict[tuple[int, str, str], dict] = {}
                    for action_idx, sel_raw, label, sig_raw, created_at in rows:
                        try:
                            idx = int(action_idx)
                        except Exception:
                            continue
                        try:
                            sel_obj = sel_raw if isinstance(sel_raw, dict) else json.loads(sel_raw)
                        except Exception:
                            continue
                        if not isinstance(sel_obj, dict):
                            continue
                        sel_type = sel_obj.get("type")
                        sel_value = sel_obj.get("value")
                        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
                            continue
                        key = (idx, sel_type, sel_value)
                        entry = stats.setdefault(key, {"passed": 0, "failed": 0})
                        lab = str(label or "").lower()
                        if lab == "passed":
                            entry["passed"] += 1
                        elif lab == "failed":
                            entry["failed"] += 1
                        if key not in sigs:
                            try:
                                sig_obj = sig_raw if isinstance(sig_raw, dict) else json.loads(sig_raw)
                            except Exception:
                                sig_obj = None
                            if isinstance(sig_obj, dict):
                                sigs[key] = sig_obj

                    for (idx, sel_type, sel_value), sf in stats.items():
                        p = int(sf.get("passed", 0) or 0)
                        f = int(sf.get("failed", 0) or 0)
                        if p <= 0 or p < f:
                            continue
                        score = (p - f, p)
                        existing = out.get(idx)
                        if existing is not None:
                            prev_p = int(existing.get("_passed", 0))
                            prev_f = int(existing.get("_failed", 0))
                            prev_score = (prev_p - prev_f, prev_p)
                            if prev_score >= score:
                                continue
                        sig_obj = sigs.get((idx, sel_type, sel_value)) or {}
                        attrs = sig_obj.get("attrs") if isinstance(sig_obj, dict) else None
                        tag = sig_obj.get("tag") if isinstance(sig_obj, dict) else None
                        out[idx] = {
                            "type": sel_type,
                            "value": sel_value,
                            "attrs": attrs if isinstance(attrs, dict) else None,
                            "tag": tag if isinstance(tag, str) else None,
                            "_passed": p,
                            "_failed": f,
                        }
        except Exception:
            return {}
        # Strip internal stats before returning.
        for k, v in list(out.items()):
            if isinstance(v, dict):
                v.pop("_passed", None)
                v.pop("_failed", None)
                if "attrs" in v and not isinstance(v.get("attrs"), dict):
                    v.pop("attrs", None)
                if "tag" in v and not isinstance(v.get("tag"), str):
                    v.pop("tag", None)
        return out

    # ---- Suites ----
    def save_suite(self, suite_id: str, spec: dict, *, tenant_id: str | None = None) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO suites(suite_id, spec, tenant_id) VALUES (%s, %s::jsonb, %s)
                    ON CONFLICT (suite_id) DO UPDATE SET spec=EXCLUDED.spec, tenant_id=COALESCE(EXCLUDED.tenant_id, suites.tenant_id), updated_at=NOW()
                    """,
                    (suite_id, json.dumps(spec), tenant_id),
                )

    def get_suite(self, suite_id: str) -> Optional[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT suite_id, spec, tenant_id FROM suites WHERE suite_id=%s", (suite_id,))
                row = cur.fetchone()
                if not row:
                    return None
                spec = row[1] if isinstance(row[1], dict) else (json.loads(row[1]) if row[1] else {})
                return {"suite_id": row[0], "spec": spec, "tenant_id": row[2]}

    def delete_suite(self, suite_id: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM suites WHERE suite_id=%s", (suite_id,))

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
                # Propagate tenant_id + suite fields from queue payload to runs row
                try:
                    cur.execute("SELECT payload FROM queue WHERE job_id=%s", (job_id,))
                    row = cur.fetchone()
                    payload = None
                    if row:
                        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    if payload and run_id:
                        try:
                            tenant_id = payload.get("tenant_id")
                            if tenant_id:
                                cur.execute(
                                    "UPDATE runs SET tenant_id=%s WHERE run_id=%s",
                                    (str(tenant_id), run_id),
                                )
                        except Exception:
                            pass
                        try:
                            fields = None
                            if isinstance(payload.get("fields"), dict):
                                fields = payload.get("fields")
                            spec = payload.get("spec") if isinstance(payload, dict) else None
                            if isinstance(spec, dict) and isinstance(spec.get("fields"), dict):
                                fields = dict(spec.get("fields") or {})
                            if isinstance(fields, dict):
                                cur.execute(
                                    "UPDATE runs SET fields=%s::jsonb WHERE run_id=%s",
                                    (json.dumps(fields), run_id),
                                )
                        except Exception:
                            pass
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

    # ---- Retrieval Embeddings ----
    def _vector_literal(self, vec: list[float] | None) -> str:
        try:
            vals = [str(float(x)) for x in (vec or [])]
        except Exception:
            vals = []
        return "[" + ",".join(vals) + "]"

    def save_embedding_selector(
        self,
        *,
        domain: str | None,
        tool: str,
        target_signature: dict,
        selector: dict,
        tenant_id: str | None = None,
        vector: list[float] | None = None,
    ) -> None:
        try:
            if vector is None:
                from engine.core.retrieval.embed import embed_signature

                vector = embed_signature(target_signature)
            with self._conn() as conn:
                with conn.cursor() as cur:
                    payload = (
                        tenant_id,
                        domain,
                        tool,
                        json.dumps(target_signature or {}),
                        json.dumps({"type": selector.get("type"), "value": selector.get("value")}),
                        json.dumps(vector or []),
                    )
                    # Prefer pgvector column when available; fall back to JSONB-only
                    try:
                        cur.execute(
                            """
                            INSERT INTO retrieval_embeddings(tenant_id, domain, tool, target_signature, selector, vector, vec)
                            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::vector)
                            """,
                            payload + (self._vector_literal(vector or []),),
                        )
                    except Exception:
                        cur.execute(
                            """
                            INSERT INTO retrieval_embeddings(tenant_id, domain, tool, target_signature, selector, vector)
                            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                            """,
                            payload,
                        )
        except Exception:
            return None

    def retrieve_embedding_selector(
        self,
        *,
        domain: str | None,
        tool: str,
        target_signature: dict,
        tenant_id: str | None = None,
        top_k: int = 5,
    ) -> dict | None:
        try:
            from engine.core.retrieval.embed import embed_signature, cosine

            qv = embed_signature(target_signature or {})
            rows: list[tuple] = []
            with self._conn() as conn:
                with conn.cursor() as cur:
                    # Prefer pgvector distance when available; fall back to JSONB vectors
                    try:
                        if tenant_id is not None:
                            cur.execute(
                                """
                                SELECT selector FROM retrieval_embeddings
                                WHERE tool=%s AND (tenant_id IS NOT DISTINCT FROM %s) AND (domain IS NOT DISTINCT FROM %s) AND vec IS NOT NULL
                                ORDER BY vec <-> %s::vector
                                LIMIT %s
                                """,
                                (
                                    tool,
                                    tenant_id,
                                    domain,
                                    self._vector_literal(qv),
                                    max(1, int(top_k or 5)),
                                ),
                            )
                        else:
                            cur.execute(
                                """
                                SELECT selector FROM retrieval_embeddings
                                WHERE tool=%s AND (domain IS NOT DISTINCT FROM %s) AND vec IS NOT NULL
                                ORDER BY vec <-> %s::vector
                                LIMIT %s
                                """,
                                (
                                    tool,
                                    domain,
                                    self._vector_literal(qv),
                                    max(1, int(top_k or 5)),
                                ),
                            )
                        vec_rows = cur.fetchall() or []
                        if vec_rows:
                            raw_sel = vec_rows[0][0]
                            try:
                                return json.loads(raw_sel) if isinstance(raw_sel, str) else raw_sel
                            except Exception:
                                return None
                    except Exception:
                        # Fallback to JSONB vectors and cosine in Python
                        if tenant_id is not None:
                            cur.execute(
                                """
                                SELECT selector, vector FROM retrieval_embeddings
                                WHERE tool=%s AND (tenant_id IS NOT DISTINCT FROM %s) AND (domain IS NOT DISTINCT FROM %s)
                                ORDER BY created_at DESC LIMIT 200
                                """,
                                (tool, tenant_id, domain),
                            )
                        else:
                            cur.execute(
                                """
                                SELECT selector, vector FROM retrieval_embeddings
                                WHERE tool=%s AND (domain IS NOT DISTINCT FROM %s)
                                ORDER BY created_at DESC LIMIT 200
                                """,
                                (tool, domain),
                            )
                        rows = cur.fetchall() or []
            best = None
            best_s = -1.0
            for sel_json, vec_json in rows:
                try:
                    sel = json.loads(sel_json) if isinstance(sel_json, str) else sel_json
                except Exception:
                    sel = None
                try:
                    vec = json.loads(vec_json) if isinstance(vec_json, str) else vec_json
                except Exception:
                    vec = None
                if not isinstance(sel, dict) or not isinstance(vec, list):
                    continue
                s = cosine(qv, [float(x) for x in vec])
                if s > best_s:
                    best_s = s
                    best = sel
            return best
        except Exception:
            return None

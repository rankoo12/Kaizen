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
        ddl_runs = (
            """
            CREATE TABLE IF NOT EXISTS runs (
              id SERIAL PRIMARY KEY,
              run_id TEXT UNIQUE,
              test_id TEXT,
              started_at TIMESTAMPTZ DEFAULT NOW(),
              finished_at TIMESTAMPTZ,
              stats JSONB
            );
            """
        )
        ddl_profiles = (
            """
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
            """
        )
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl_runs)
                cur.execute(ddl_profiles)

    # ---- Run lifecycle (compat with orchestrator) ----
    def start_run(self, test_id: str) -> str:
        run_id = f"run-{int(time.time())}-{test_id}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO runs(run_id, test_id) VALUES (%s, %s) ON CONFLICT (run_id) DO NOTHING",
                    (run_id, test_id),
                )
        return run_id

    def record_step(self, step: dict) -> None:
        # Not persisted yet; placeholder for future expanded schema
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

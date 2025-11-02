from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI, HTTPException, Query

import engine.core.reporting.reporter as reporter_mod


_SEEN_RUN_IDS: set[str] = set()


def register_run_routes(app: FastAPI, orchestrator) -> None:
    """Register minimal run endpoints using the existing orchestrator.

    - POST /api/runs: accepts a payload with a `spec` object and optional
      execution hints; returns a `run_id`.
    - GET /api/runs/{id}: returns run status and minimal stats if finished.
    """

    router = APIRouter(prefix="/api", tags=["runs"])

    @router.get("/runs")
    async def list_runs(
        mode: str | None = Query(default=None, description="Filter by mode: live|snapshot"),
        limit: int = Query(default=50, ge=1, le=200),
        since: float | None = Query(default=None, description="Unix epoch seconds; include runs started at or after"),
        offset: int = Query(default=0, ge=0, description="Offset for simple pagination"),
    ):
        """List recent runs from reporter; best-effort DB fallback when available.

        - Sorted by started (desc) where available; otherwise preserve insertion order.
        - Mode filter applies to in-memory reporter data.
        - "since" filter compares against reporter "started" timestamps when present, or DB started_at.
        """
        rep = reporter_mod.RUN_REPORTER
        runs: List[dict] = []

        # Prefer in-memory reporter which has richer rollups
        try:
            all_runs = list(getattr(rep, "_runs", []) or [])
            # sort desc by started if present
            try:
                all_runs.sort(key=lambda r: float(r.get("started", 0) or 0), reverse=True)
            except Exception:
                pass
            # apply filters
            if mode:
                m = str(mode).lower()
                all_runs = [r for r in all_runs if str(r.get("mode") or "").lower() == m]
            if since is not None:
                try:
                    s = float(since)
                    all_runs = [r for r in all_runs if float(r.get("started", 0) or 0) >= s]
                except Exception:
                    pass
            total = len(all_runs)
            window = all_runs[offset : offset + limit]
            runs = [
                {
                    "run_id": r.get("run_id"),
                    "mode": r.get("mode"),
                    "started": r.get("started"),
                    "stats": r.get("stats", {}),
                    "by_tool": r.get("by_tool", {}),
                }
                for r in window
            ]
            return {"runs": runs, "total": total, "offset": offset, "limit": limit}
        except Exception:
            runs = []

        # Fallback: best-effort DB query when reporter not available
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
            if hasattr(st, "_conn"):
                args: list[Any] = []
                sql = (
                    "SELECT run_id, test_id, extract(epoch from started_at) as started, extract(epoch from finished_at) as finished, stats "
                    "FROM runs"
                )
                where = []
                if since is not None:
                    where.append("started_at >= to_timestamp(%s)")
                    args.append(float(since))
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY started_at DESC LIMIT %s OFFSET %s"
                args.extend([int(limit), int(offset)])
                out = []
                with st._conn() as conn:  # type: ignore[attr-defined]
                    with conn.cursor() as cur:
                        cur.execute(sql, tuple(args))
                        for row in cur.fetchall():
                            out.append(
                                {
                                    "run_id": row[0],
                                    "mode": None,
                                    "started": float(row[2]) if row[2] is not None else None,
                                    "stats": row[4] or {},
                                    "by_tool": {},
                                }
                            )
                return {"runs": out, "total": len(out), "offset": offset, "limit": limit}
        except Exception:
            pass
        return {"runs": [], "total": 0, "offset": offset, "limit": limit}

    @router.post("/runs")
    async def create_run(body: Dict[str, Any]):
        mode = str(body.get("mode") or "snapshot").lower()
        spec = body.get("spec") or {}

        try:
            if mode == "live":
                url = body.get("url")
                run_id = orchestrator.run_live(spec, url=url)
            else:
                run_id = orchestrator.run_snapshot(
                    spec,
                    html_path=body.get("html_path"),
                    html=body.get("html"),
                    snapshot_path=body.get("snapshot") or body.get("snapshot_path"),
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"run error: {e!s}")

        return {"run_id": run_id}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        rep = reporter_mod.RUN_REPORTER

        # Check finished runs first
        try:
            for r in getattr(rep, "_runs", []) or []:
                if str(r.get("run_id")) == str(run_id):
                    return {
                        "run_id": run_id,
                        "status": "finished",
                        "stats": r.get("stats", {}),
                        "mode": r.get("mode"),
                        "started": r.get("started"),
                        "by_tool": r.get("by_tool", {}),
                        "fields": r.get("fields", {}),
                    }
        except Exception:
            pass

        # Then check currently open (running) runs
        try:
            cur = getattr(rep, "_open", {}).get(str(run_id))
            if cur is not None:
                by_tool = {t: dict(rc) for t, rc in (cur.get("by_tool") or {}).items()}
                return {
                    "run_id": run_id,
                    "status": "running",
                    "stats": {},
                    "mode": cur.get("mode"),
                    "started": cur.get("started"),
                    "by_tool": by_tool,
                    "fields": cur.get("fields", {}),
                }
        except Exception:
            pass

        return {"run_id": run_id, "status": "unknown", "stats": {}}

    @router.post("/runs/{run_id}/finish")
    async def finish_run(run_id: str, body: Dict[str, Any]):
        """Accept final stats from external runner and record in reporter."""
        stats = body.get("stats") or {}
        # guardrail: prevent duplicate run_ids
        if str(run_id) in _SEEN_RUN_IDS:
            raise HTTPException(status_code=409, detail="duplicate run_id")
        try:
            _SEEN_RUN_IDS.add(str(run_id))
            try:
                print(f"[runs] finish: run_id={run_id} stats_keys={list(stats.keys())}")
            except Exception:
                pass
            reporter_mod.RUN_REPORTER.on_run_finish(run_id, dict(stats))
            reporter_mod.RUN_REPORTER.on_finish(run_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"finish error: {e!s}")
        return {"ok": True}

    app.include_router(router)

from typing import Any, Dict

from fastapi import APIRouter, FastAPI, HTTPException

import engine.core.reporting.reporter as reporter_mod


def register_run_routes(app: FastAPI, orchestrator) -> None:
    """Register minimal run endpoints using the existing orchestrator.

    - POST /api/runs: accepts a payload with a `spec` object and optional
      execution hints; returns a `run_id`.
    - GET /api/runs/{id}: returns run status and minimal stats if finished.
    """

    router = APIRouter(prefix="/api", tags=["runs"])

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
        try:
            reporter_mod.RUN_REPORTER.on_run_finish(run_id, dict(stats))
            reporter_mod.RUN_REPORTER.on_finish(run_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"finish error: {e!s}")
        return {"ok": True}

    app.include_router(router)

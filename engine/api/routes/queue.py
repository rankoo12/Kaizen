from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, FastAPI
import itertools
import time


_COUNTER = itertools.count(1)
_QUEUE: List[Dict[str, Any]] = []
_RUNNING: Dict[str, Dict[str, Any]] = {}  # job_id -> {job_id, run_id?, ts?}
_COMPLETED: Dict[str, Dict[str, Any]] = {}  # job_id -> {job_id, run_id, ts}


def register_queue_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api", tags=["queue"])

    @router.post("/queue/runs")
    async def enqueue_run(body: Dict[str, Any]):
        job_id = f"job-{next(_COUNTER)}"
        job = {"job_id": job_id, **(body or {})}
        _QUEUE.append(job)
        try:
            print(f"[queue] enqueue job_id={job_id} keys={list((body or {}).keys())}")
        except Exception:
            pass
        return {"job_id": job_id}

    @router.get("/queue/next")
    async def next_job():
        if not _QUEUE:
            try:
                print("[queue] next: empty")
            except Exception:
                pass
            return {"job": None}
        job = _QUEUE.pop(0)
        try:
            print(f"[queue] next: dispatch job_id={job.get('job_id')}")
        except Exception:
            pass
        return {"job": job}

    @router.post("/queue/running")
    async def mark_running(body: Dict[str, Any]):
        job_id = str(body.get("job_id")) if body else None
        if not job_id:
            return {"ok": False, "error": "job_id required"}
        run_id = body.get("run_id")
        rec = _RUNNING.get(job_id) or {"job_id": job_id}
        if run_id:
            rec["run_id"] = str(run_id)
        _RUNNING[job_id] = rec
        try:
            print(f"[queue] running: job_id={job_id} run_id={rec.get('run_id')}")
        except Exception:
            pass
        return {"ok": True, "running": rec}

    @router.post("/queue/complete")
    async def mark_complete(body: Dict[str, Any]):
        job_id = str(body.get("job_id")) if body else None
        if not job_id:
            return {"ok": False, "error": "job_id required"}
        rec = _RUNNING.pop(job_id, None)
        run_id = body.get("run_id")
        if run_id:
            _COMPLETED[job_id] = {"job_id": job_id, "run_id": str(run_id), "ts": time.time()}
        try:
            print(f"[queue] complete: job_id={job_id} run_id={run_id}")
        except Exception:
            pass
        return {"ok": True}

    @router.get("/queue/state")
    async def get_state():
        queued = [{"job_id": j.get("job_id")} for j in list(_QUEUE)]
        running = list(_RUNNING.values())
        # include recent completions (best-effort), most-recent first
        completed = sorted(_COMPLETED.values(), key=lambda r: r.get("ts", 0), reverse=True)[:50]
        return {"queued": queued, "running": running, "completed": completed}

    @router.get("/queue/completed/{job_id}")
    async def get_completed(job_id: str):
        rec = _COMPLETED.get(str(job_id))
        return {"job": rec}

    app.include_router(router)

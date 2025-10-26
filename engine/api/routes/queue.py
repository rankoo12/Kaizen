from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, FastAPI
import itertools


_COUNTER = itertools.count(1)
_QUEUE: List[Dict[str, Any]] = []


def register_queue_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api", tags=["queue"])

    @router.post("/queue/runs")
    async def enqueue_run(body: Dict[str, Any]):
        job_id = f"job-{next(_COUNTER)}"
        job = {"job_id": job_id, **(body or {})}
        _QUEUE.append(job)
        return {"job_id": job_id}

    @router.get("/queue/next")
    async def next_job():
        if not _QUEUE:
            return {"job": None}
        job = _QUEUE.pop(0)
        return {"job": job}

    app.include_router(router)

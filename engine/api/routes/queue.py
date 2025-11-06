from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, FastAPI, Request, HTTPException
import itertools
import time


_COUNTER = itertools.count(1)
_QUEUE: List[Dict[str, Any]] = []
_RUNNING: Dict[str, Dict[str, Any]] = {}  # job_id -> {job_id, run_id?, ts?}
_COMPLETED: Dict[str, Dict[str, Any]] = {}  # job_id -> {job_id, run_id, ts}


def register_queue_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api", tags=["queue"])
    # Optional Postgres-backed storage for durable queue
    _storage = None
    try:
        from engine.core.config.container import Container  # lazy import
        _storage = Container().storage()
    except Exception:
        _storage = None

    def _inject_traceparent(job: Dict[str, Any]) -> None:
        try:
            # Use global propagator (W3C tracecontext) to inject current context
            from opentelemetry.propagate import inject  # type: ignore
            import opentelemetry.context as context  # type: ignore

            headers: Dict[str, str] = {}
            inject(headers, context=context.get_current())
            tp = headers.get("traceparent")
            ts = headers.get("tracestate")
            if tp:
                job["traceparent"] = tp
            if ts:
                job["tracestate"] = ts
        except Exception:
            # Safe no-op when OTel not present
            pass

    # Phase 2 metrics: Observable gauge for queue depth
    try:
        from opentelemetry import metrics as _metrics
        _METER = _metrics.get_meter("kaizen.engine.queue")

        # OTel stable (>=1.17) style callback: accepts CallbackOptions and returns list[Observation]
        try:
            from opentelemetry.metrics import Observation  # type: ignore

            def _observe_queue_depth(options=None):  # options: CallbackOptions
                try:
                    return [
                        Observation(len(_QUEUE), {"state": "queued"}),
                        Observation(len(_RUNNING), {"state": "running"}),
                    ]
                except Exception:
                    return []

            _METER.create_observable_gauge(
                name="kaizen_queue_depth",
                callbacks=[_observe_queue_depth],
                description="Number of jobs queued/running",
            )
        except Exception:
            # Fallback to older observer.observe signature if available
            try:
                def _observe_legacy(observer):
                    try:
                        observer.observe(len(_QUEUE), {"state": "queued"})
                        observer.observe(len(_RUNNING), {"state": "running"})
                    except Exception:
                        pass

                _METER.create_observable_gauge(
                    name="kaizen_queue_depth",
                    callbacks=[_observe_legacy],
                    description="Number of jobs queued/running",
                )
            except Exception:
                pass
    except Exception:
        pass

    @router.post("/queue/runs")
    async def enqueue_run(body: Dict[str, Any], request: Request):
        # Prefer durable queue when available
        if _storage is not None and hasattr(_storage, "enqueue"):
            # Enforce API key if multitenancy is enabled
            try:
                from engine.core.config.settings import settings as _settings

                if getattr(_settings, "MULTITENANT_ENFORCED", False):
                    api_key = request.headers.get("X-API-Key") if request else None
                    resolver = getattr(_storage, "resolve_tenant", None)
                    tenant_check = resolver(api_key) if callable(resolver) else None
                    if not tenant_check:
                        raise HTTPException(status_code=401, detail="unauthorized")
            except Exception:
                pass
            payload = dict(body or {})
            # Attach tenant_id from API key if resolvable
            try:
                api_key = request.headers.get("X-API-Key")
                res = getattr(_storage, "resolve_tenant", None)
                if callable(res):
                    tenant_id = res(api_key)
                    if tenant_id:
                        payload["tenant_id"] = tenant_id
            except Exception:
                pass
            _inject_traceparent(payload)
            try:
                job_id = _storage.enqueue(payload)
            except Exception:
                job_id = None
            if not job_id:
                return {"error": "enqueue_failed"}
            try:
                print(f"[queue] enqueue pg job_id={job_id}")
            except Exception:
                pass
            return {"job_id": job_id}
        # In-memory fallback
        job_id = f"job-{next(_COUNTER)}"
        job = {"job_id": job_id, **(body or {})}
        _inject_traceparent(job)
        _QUEUE.append(job)
        try:
            print(f"[queue] enqueue job_id={job_id} keys={list((body or {}).keys())}")
        except Exception:
            pass
        return {"job_id": job_id}

    @router.get("/queue/next")
    async def next_job():
        if _storage is not None and hasattr(_storage, "next_job"):
            try:
                job = _storage.next_job()
            except Exception:
                job = None
            if not job:
                try:
                    print("[queue] next pg: empty")
                except Exception:
                    pass
                return {"job": None}
            try:
                print(f"[queue] next pg: dispatch job_id={job.get('job_id')}")
            except Exception:
                pass
            return {"job": job}
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

    @router.post("/queue/sample")
    async def enqueue_sample(kind: str = "snapshot"):
        """Enqueue a deterministic sample run to exercise tracing.

        - Snapshot mode with small inline HTML and two key presses to produce step spans.
        """
        job_id = f"job-{next(_COUNTER)}"
        if str(kind).lower() != "live":
            job = {
                "job_id": job_id,
                "mode": "snapshot",
                "spec": {"id": f"sample-{int(time.time())}", "steps": [{"text": "press Enter"}, {"text": "press Escape"}]},
                "html": "<html><body><h1>Hello Kaizen</h1></body></html>",
            }
        else:
            job = {
                "job_id": job_id,
                "mode": "live",
                "spec": {"id": f"sample-{int(time.time())}", "steps": [{"text": "press Enter"}]},
                "url": "about:blank",
            }
        _inject_traceparent(job)
        if _storage is not None and hasattr(_storage, "enqueue"):
            try:
                jid = _storage.enqueue(job)
                if jid:
                    job_id = jid
            except Exception:
                pass
        else:
            _QUEUE.append(job)
        try:
            print(f"[queue] enqueue sample job_id={job_id} kind={kind}")
        except Exception:
            pass
        return {"job_id": job_id, "job": job}

    @router.post("/queue/running")
    async def mark_running(body: Dict[str, Any]):
        job_id = str(body.get("job_id")) if body else None
        if not job_id:
            return {"ok": False, "error": "job_id required"}
        run_id = body.get("run_id")
        if _storage is not None and hasattr(_storage, "mark_running"):
            try:
                _storage.mark_running(job_id, run_id=str(run_id) if run_id else None)
            except Exception:
                return {"ok": False}
            rec = {"job_id": job_id}
            if run_id:
                rec["run_id"] = str(run_id)
        else:
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
        if _storage is not None and hasattr(_storage, "complete"):
            try:
                _storage.complete(job_id, run_id=str(run_id) if run_id else None)
            except Exception:
                return {"ok": False}
        elif run_id:
            _COMPLETED[job_id] = {"job_id": job_id, "run_id": str(run_id), "ts": time.time()}
        try:
            print(f"[queue] complete: job_id={job_id} run_id={run_id}")
        except Exception:
            pass
        return {"ok": True}

    @router.get("/queue/state")
    async def get_state(request: Request):
        if _storage is not None and hasattr(_storage, "state"):
            try:
                api_key = request.headers.get("X-API-Key")
                res = getattr(_storage, "resolve_tenant", None)
                tenant_id = res(api_key) if callable(res) else None
                # If multitenancy is enforced, reject when no tenant is found
                try:
                    from engine.core.config.settings import settings as _settings

                    if getattr(_settings, "MULTITENANT_ENFORCED", False) and tenant_id is None:
                        raise HTTPException(status_code=401, detail="unauthorized")
                except Exception:
                    pass
                return _storage.state(tenant=tenant_id)
            except Exception:
                pass
        queued = [{"job_id": j.get("job_id")} for j in list(_QUEUE)]
        running = list(_RUNNING.values())
        completed = sorted(_COMPLETED.values(), key=lambda r: r.get("ts", 0), reverse=True)[:50]
        return {"queued": queued, "running": running, "completed": completed}

    @router.get("/queue/completed/{job_id}")
    async def get_completed(job_id: str):
        if _storage is not None and hasattr(_storage, "state"):
            st = _storage.state()
            rec = next((j for j in st.get("completed", []) if str(j.get("job_id")) == str(job_id)), None)
            return {"job": rec}
        rec = _COMPLETED.get(str(job_id))
        return {"job": rec}

    app.include_router(router)

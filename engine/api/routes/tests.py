from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, FastAPI, HTTPException, Request


# Minimal in-memory tests store (contract-style Test objects)
_TESTS: Dict[str, Dict[str, Any]] = {}


def _normalize_test(body: Dict[str, Any]) -> Dict[str, Any]:
    # Accept either {test: {...}} or the test object directly
    if not isinstance(body, dict):
        return {}
    test = body.get("test") if isinstance(body.get("test"), dict) else None
    return test or body


def _get_test_id(test: Dict[str, Any]) -> str | None:
    tid = test.get("id") or test.get("name")
    return str(tid) if tid else None


def register_test_routes(app: FastAPI, orchestrator) -> None:
    """Register contract-style Test authoring and run endpoints.

    Test objects follow CONTRACT.md section 1:
      { id, name, description?, app_base_url?, tags?, steps: [ {id,index,text,expected?} ] }
    """

    router = APIRouter(prefix="/api", tags=["tests"])

    @router.post("/tests", status_code=201)
    async def create_test(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
        test = _normalize_test(body)
        test_id = _get_test_id(test)
        if not test_id:
            raise HTTPException(status_code=422, detail="test id required (id or name)")
        # Prefer storage when available (re-use suites table)
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "save_suite"):
            tenant_id = None
            try:
                from engine.core.config.settings import settings as _settings

                if getattr(_settings, "MULTITENANT_ENFORCED", False) and request is not None:
                    res = getattr(st, "resolve_tenant", None)
                    tenant_id = res(request.headers.get("X-API-Key")) if callable(res) else None
                    if tenant_id is None:
                        raise HTTPException(status_code=401, detail="unauthorized")
            except HTTPException:
                raise
            except Exception:
                tenant_id = None
            try:
                st.save_suite(str(test_id), test, tenant_id=tenant_id)  # type: ignore[call-arg]
            except TypeError:
                st.save_suite(str(test_id), test)
        else:
            _TESTS[str(test_id)] = test
        return {"test_id": str(test_id)}

    @router.get("/tests/{test_id}")
    async def get_test(request: Request, test_id: str) -> Dict[str, Any]:
        # Prefer storage when available
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "get_suite"):
            try:
                from engine.core.config.settings import settings as _settings

                if getattr(_settings, "MULTITENANT_ENFORCED", False) and request is not None:
                    res = getattr(st, "resolve_tenant", None)
                    tid = res(request.headers.get("X-API-Key")) if callable(res) else None
                    if tid is None:
                        raise HTTPException(status_code=401, detail="unauthorized")
            except HTTPException:
                raise
            except Exception:
                pass
            row = st.get_suite(str(test_id))
            if row is None:
                raise HTTPException(status_code=404, detail="test not found")
            # Hide tests belonging to other tenants when enforced
            try:
                from engine.core.config.settings import settings as _settings

                if getattr(_settings, "MULTITENANT_ENFORCED", False):
                    res = getattr(st, "resolve_tenant", None)
                    req_tid = res(request.headers.get("X-API-Key")) if callable(res) and request is not None else None
                    if row.get("tenant_id") is not None and row.get("tenant_id") != req_tid:
                        raise HTTPException(status_code=404, detail="test not found")
            except HTTPException:
                raise
            except Exception:
                pass
            return {"test_id": row.get("suite_id"), "test": row.get("spec")}
        # In-memory fallback
        test = _TESTS.get(str(test_id))
        if test is None:
            raise HTTPException(status_code=404, detail="test not found")
        return {"test_id": str(test_id), "test": test}

    @router.post("/tests/{test_id}/runs")
    async def run_test(test_id: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        Enqueue a test run instead of executing synchronously on the API server.

        This mirrors /api/runs queue-first behavior so the API event loop stays free.
        """
        body = body or {}
        # Resolve test spec from storage or in-memory map
        test_spec: Dict[str, Any] | None = None
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "get_suite"):
            row = st.get_suite(str(test_id))
            if row is not None:
                test_spec = row.get("spec") or {}
        if test_spec is None:
            test_spec = _TESTS.get(str(test_id))
        if not isinstance(test_spec, dict):
            raise HTTPException(status_code=404, detail="test not found")
        # Optional per-run metadata (e.g. suite_id, tags) coming from the caller
        # or the test spec itself. When provided, merge into spec.fields so the
        # reporter can expose it via run.fields in /api/runs.
        extra_fields = {}
        try:
            raw_fields = body.get("fields")
            if isinstance(raw_fields, dict):
                extra_fields = dict(raw_fields)
        except Exception:
            extra_fields = {}
        # Ensure tags and test identifiers from the stored test spec are
        # visible on runs for filtering in the Portal UI.
        try:
            if isinstance(test_spec, dict):
                tags = test_spec.get("tags")
                if isinstance(tags, list) and tags:
                    extra_fields = dict(extra_fields)
                    if "tags" not in extra_fields:
                        extra_fields["tags"] = tags
                # Attach a stable test identifier so dashboards and the
                # Runs page can avoid "Unknown" entries when stats lack
                # a test_name field.
                test_ident = test_spec.get("id") or test_spec.get("name")
                if test_ident and "test_id" not in extra_fields:
                    extra_fields = dict(extra_fields)
                    extra_fields["test_id"] = str(test_ident)
                test_name = test_spec.get("name")
                if test_name and "test_name" not in extra_fields:
                    extra_fields = dict(extra_fields)
                    extra_fields["test_name"] = str(test_name)
        except Exception:
            pass
        if extra_fields:
            spec = dict(test_spec)
            merged_fields = {}
            try:
                if isinstance(spec.get("fields"), dict):
                    merged_fields.update(spec["fields"])  # type: ignore[arg-type]
            except Exception:
                pass
            merged_fields.update(extra_fields)
            spec["fields"] = merged_fields
            test_spec = spec

        mode = str(body.get("mode") or "live").lower()
        payload: Dict[str, Any] = {
            "mode": mode,
            "spec": test_spec,
            "html_path": body.get("html_path"),
            "html": body.get("html"),
            "snapshot": body.get("snapshot") or body.get("snapshot_path"),
            "snapshot_path": body.get("snapshot_path"),
            "url": body.get("url") or test_spec.get("app_base_url"),
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        job_id: str | None = None

        # Prefer durable queue when available
        try:
            if st is not None and hasattr(st, "enqueue"):
                job_id = st.enqueue(payload)  # type: ignore[call-arg]
        except Exception:
            job_id = None

        # In-memory queue fallback (shared with /api/queue routes)
        if not job_id:
            try:
                from engine.api.routes import queue as queue_routes

                job_id = f"job-{next(queue_routes._COUNTER)}"
                job = {"job_id": job_id, **payload}
                queue_routes._QUEUE.append(job)
            except Exception:
                job_id = None

        if not job_id:
            raise HTTPException(status_code=500, detail="run enqueue failed")

        return {"job_id": job_id, "run_id": None, "status": "queued"}

    app.include_router(router)

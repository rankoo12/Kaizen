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

        mode = str(body.get("mode") or "live").lower()
        try:
            if mode == "snapshot":
                run_id = orchestrator.run_snapshot(
                    test_spec,
                    html_path=body.get("html_path"),
                    html=body.get("html"),
                    snapshot_path=body.get("snapshot") or body.get("snapshot_path"),
                )
            else:
                url = body.get("url") or test_spec.get("app_base_url")
                if not isinstance(url, str) or not url:
                    raise HTTPException(status_code=422, detail="url or app_base_url required for live mode")
                run_id = orchestrator.run_live(test_spec, url=url)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"run error: {e!s}")
        return {"run_id": run_id}

    app.include_router(router)

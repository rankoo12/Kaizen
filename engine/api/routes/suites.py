from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, FastAPI, HTTPException, Request


# Minimal in-memory suites store
_SUITES: Dict[str, Dict[str, Any]] = {}


def _get_suite_id(body: Dict[str, Any]) -> str | None:
    # Prefer explicit id at top-level, then spec.id/name
    sid = body.get("id")
    if sid:
        return str(sid)
    spec = body.get("spec") or body
    sid = spec.get("id") or spec.get("name")
    return str(sid) if sid else None


def _normalize_spec(body: Dict[str, Any]) -> Dict[str, Any]:
    # Accept either {spec: {...}} or the spec object directly
    spec = body.get("spec") if isinstance(body, dict) else None
    if not spec and isinstance(body, dict):
        spec = {k: v for k, v in body.items() if k != "id"}
    return spec or {}


def register_suite_routes(app: FastAPI, orchestrator) -> None:
    router = APIRouter(prefix="/api", tags=["suites"])

    @router.post("/suites")
    async def create_suite(request: Request, body: Dict[str, Any]):
        suite_id = _get_suite_id(body)
        if not suite_id:
            raise HTTPException(status_code=422, detail="suite id required (id or spec.id)")
        spec = _normalize_spec(body)
        # Prefer storage when available
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "save_suite"):
            # Resolve tenant from API key when possible
            tenant_id = None
            try:
                res = getattr(st, "resolve_tenant", None)
                if callable(res) and request is not None:
                    tenant_id = res(request.headers.get("X-API-Key"))
            except Exception:
                tenant_id = None
            try:
                # New signature with tenant support
                st.save_suite(str(suite_id), spec, tenant_id=tenant_id)  # type: ignore[call-arg]
            except TypeError:
                st.save_suite(str(suite_id), spec)
        else:
            _SUITES[str(suite_id)] = spec
        return {"suite_id": str(suite_id)}

    @router.get("/suites/{suite_id}")
    async def get_suite(request: Request, suite_id: str):
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "get_suite"):
            # Enforce tenant isolation when enabled
            try:
                from engine.core.config.settings import settings as _settings
                if getattr(_settings, "MULTITENANT_ENFORCED", False):
                    res = getattr(st, "resolve_tenant", None)
                    if callable(res) and request is not None:
                        tid = res(request.headers.get("X-API-Key"))
                        if tid is None:
                            raise HTTPException(status_code=401, detail="unauthorized")
            except HTTPException:
                raise
            except Exception:
                pass
            row = st.get_suite(str(suite_id))
            if row is None:
                raise HTTPException(status_code=404, detail="suite not found")
            # If enforced, hide suites from other tenants
            try:
                from engine.core.config.settings import settings as _settings
                if getattr(_settings, "MULTITENANT_ENFORCED", False):
                    # request tenant id
                    res = getattr(st, "resolve_tenant", None)
                    req_tid = res(request.headers.get("X-API-Key")) if callable(res) and request is not None else None
                    if row.get("tenant_id") is not None and row.get("tenant_id") != req_tid:
                        raise HTTPException(status_code=404, detail="suite not found")
            except HTTPException:
                raise
            except Exception:
                pass
            return {"suite_id": row.get("suite_id"), "spec": row.get("spec")}
        # In-memory fallback
        spec = _SUITES.get(str(suite_id))
        if spec is None:
            raise HTTPException(status_code=404, detail="suite not found")
        return {"suite_id": suite_id, "spec": spec}

    @router.post("/suites/{suite_id}/runs")
    async def run_suite(suite_id: str, body: Dict[str, Any] | None = None):
        spec = _SUITES.get(str(suite_id))
        if spec is None:
            raise HTTPException(status_code=404, detail="suite not found")
        body = body or {}
        mode = str(body.get("mode") or "snapshot").lower()
        try:
            if mode == "live":
                run_id = orchestrator.run_live(spec, url=body.get("url"))
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

    app.include_router(router)

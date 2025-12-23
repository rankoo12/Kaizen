from typing import Any, Dict
import time

import os
import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/suites", tags=["suites"])

ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")

# Portal-local suites store so we can keep UX simple without
# depending on engine /api/suites run semantics.
_PORTAL_SUITES: Dict[str, Dict[str, Any]] = {}


@router.post("", status_code=201)
def create_suite(request: Request, body: Dict[str, Any] | None = None):
    """Create or update a suite for the current tenant.

    Persist the suite spec locally inside the portal process and
    best-effort mirror it to the Engine API.
    """
    body = body or {}
    suite_id = body.get("id") or (body.get("spec") or {}).get("id") or body.get("name")
    if not suite_id:
        raise HTTPException(status_code=422, detail="'id' or spec.id is required")
    spec = body.get("spec") or {}
    if not isinstance(spec, dict):
        raise HTTPException(status_code=422, detail="'spec' must be an object")

    suite_id_str = str(suite_id)
    # Cache locally for Portal UX
    _PORTAL_SUITES[suite_id_str] = dict(spec, id=suite_id_str)

    # Best-effort mirror to engine so suites are visible to backend tooling;
    # failures here should not block the Portal UX.
    headers: Dict[str, str] = {}
    try:
        if request.headers.get("X-API-Key"):
            headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
        headers = {}
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"{ENGINE_API_BASE}/suites",
                json={"id": suite_id_str, "spec": spec},
                headers=headers or None,
            )
    except Exception:
        # Soft-fail: keep local suite only
        pass

    return {"suiteId": suite_id_str}


@router.get("")
def list_suites() -> Dict[str, Any]:
    """List suites known to the Portal.

    Suites are stored in the Engine's suites table via /api/suites.
    For UX we pull from there and merge in any Portal-local suites.
    """
    items: list[Dict[str, Any]] = []

    # Prefer Engine-backed suites list
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{ENGINE_API_BASE}/suites", params={"limit": 200})
            r.raise_for_status()
            data = r.json()
            for row in data.get("items") or []:
                spec = row.get("spec") or {}
                if not isinstance(spec, dict):
                    continue
                tests = spec.get("tests") or []
                # Heuristic: treat rows with a non-empty "tests" array as suites
                if not isinstance(tests, list) or not tests:
                    continue
                sid = spec.get("id") or row.get("suite_id")
                if not sid:
                    continue
                spec = dict(spec)
                spec["id"] = str(sid)
                items.append(spec)
    except Exception:
        items = []

    # Merge in Portal-local suites where not already present
    for sid, spec in _PORTAL_SUITES.items():
        if not any(str(it.get("id")) == str(sid) for it in items):
            items.append(dict(spec))

    return {"items": items}


@router.post("/{suite_id}/runs", status_code=201)
def run_suite(request: Request, suite_id: str, body: Dict[str, Any] | None = None):
    """Run all tests in a suite by starting runs for each test id.

    We treat suite.spec.tests as a list of test IDs and call the Engine
    /api/tests/{id}/runs endpoint for each. This keeps semantics clear and
    avoids relying on Engine /api/suites/{id}/runs, which is currently
    tuned for snapshot-style suite specs.
    """
    body = body or {}
    sid = str(suite_id)

    suite = _PORTAL_SUITES.get(sid)
    if not suite:
        # Fallback: fetch from Engine suites table
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{ENGINE_API_BASE}/suites/{sid}")
                if r.status_code == 200:
                    row = r.json()
                    suite = (row.get("spec") or {}) if isinstance(row, dict) else None
        except Exception:
            suite = None
    if not isinstance(suite, dict):
        raise HTTPException(status_code=404, detail="suite not found")

    tests = suite.get("tests") or []
    if not isinstance(tests, list) or not tests:
        raise HTTPException(status_code=422, detail="suite has no tests")

    mode = str(body.get("mode") or "live").lower()
    suite_name = str(suite.get("name") or sid)
    # Tag all runs from the same invocation with a shared suite_run_id so
    # the dashboard can group them together.
    suite_run_id = f"{sid}-{int(time.time())}"

    headers: Dict[str, str] = {}
    try:
        if request.headers.get("X-API-Key"):
            headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
        headers = {}

    run_ids: list[str] = []
    errors: list[dict[str, str]] = []
    with httpx.Client(timeout=30.0) as client:
        for test_id in tests:
            tid = str(test_id)
            try:
                resp = client.post(
                    f"{ENGINE_API_BASE}/tests/{tid}/runs",
                    json={
                        "mode": mode,
                        "fields": {
                            "suite_id": sid,
                            "suite_name": suite_name,
                            "suite_run_id": suite_run_id,
                            "test_id": tid,
                        },
                    },
                    headers=headers or None,
                )
                resp.raise_for_status()
                data = resp.json()
                run_id = data.get("run_id")
                if run_id:
                    run_ids.append(str(run_id))
                else:
                    errors.append({"test_id": tid, "error": "missing_run_id"})
            except Exception as e:
                errors.append({"test_id": tid, "error": str(e)})
                continue

    return {"runIds": run_ids, "errors": errors}

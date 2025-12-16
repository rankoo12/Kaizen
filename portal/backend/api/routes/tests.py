from typing import Any, Dict

import os
import httpx
from fastapi import APIRouter, HTTPException, Request

# Lazy/safe import of engine parser (portal runs as a separate module)
try:
    from engine.core.parsing.nl_steps import parse_steps_text  # type: ignore
except Exception:

    def parse_steps_text(steps_text: str):
        steps = []
        if isinstance(steps_text, str):
            index = 0
            for raw in steps_text.splitlines():
                line = (raw or "").strip()
                if not line or line.startswith("#"):
                    continue
                index += 1
                steps.append(
                    {
                        "id": f"step_{index}",
                        "index": index,
                        "text": line,
                    }
                )
        return steps


router = APIRouter(prefix="/tests", tags=["tests"])

# Minimal in-memory store so the Portal UI can list
# tests created via the Portal itself.
_PORTAL_TESTS: Dict[str, Dict[str, Any]] = {}


@router.post("", status_code=201)
def create_test(request: Request, body: Dict[str, Any] | None = None):
    """Create a CONTRACT-style Test via Engine API."""
    body = body or {}
    # Allow a simpler stepsText payload from UI and normalize via parse_steps_text
    engine_payload: Dict[str, Any] = dict(body)
    if not engine_payload.get("steps"):
        steps_text = engine_payload.get("stepsText")
        if isinstance(steps_text, str):
            engine_payload["steps"] = parse_steps_text(steps_text)
            engine_payload.pop("stepsText", None)
    engine_base = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")
    headers: Dict[str, str] = {}
    try:
        if request.headers.get("X-API-Key"):
            headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
        pass
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{engine_base}/tests", json=engine_payload, headers=headers or None
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal create test error: {e!s}")
    test_id = (data.get("test_id") or body.get("id") or "").__str__()
    # Cache spec locally so the Tests page can list it
    try:
        cached = dict(engine_payload)
        cached["id"] = test_id
        _PORTAL_TESTS[test_id] = cached
    except Exception:
        pass
    return {"testId": test_id, "engine": data}


@router.get("")
def list_tests() -> Dict[str, Any]:
    """Return tests known to the Portal.

    Tests are stored in the Engine's suites table via the /api/tests
    endpoint. For UX, we combine those with any Portal-local tests
    cached in this process.
    """
    engine_base = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")
    items: list[Dict[str, Any]] = []

    # Prefer Engine-backed suites list.
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{engine_base}/suites", params={"limit": 200})
            r.raise_for_status()
            data = r.json()
            for row in data.get("items") or []:
                spec = row.get("spec") or {}
                if not isinstance(spec, dict):
                    continue
                # Heuristic: treat rows with "steps" as tests.
                steps = spec.get("steps") or []
                if not isinstance(steps, list) or not steps:
                    continue
                tid = spec.get("id") or row.get("suite_id")
                if not tid:
                    continue
                spec = dict(spec)
                spec["id"] = str(tid)
                items.append(spec)
    except Exception:
        # Soft-fail; fall back to portal-local cache only.
        items = []

    # Merge in Portal-local tests, preferring Engine-backed versions.
    for tid, spec in _PORTAL_TESTS.items():
        if not any(str(it.get("id")) == str(tid) for it in items):
            items.append(dict(spec))

    return {"items": items}


ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")


@router.get("/{test_id}")
def get_test(request: Request, test_id: str):
    """Fetch a CONTRACT-style Test from Engine API."""
    engine_base = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")
    headers: Dict[str, str] = {}
    try:
        if request.headers.get("X-API-Key"):
            headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
        pass
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{engine_base}/tests/{test_id}", headers=headers or None)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal get test error: {e!s}")
    return data


@router.post("/{test_id}/runs", status_code=201)
def run_test(request: Request, test_id: str, body: Dict[str, Any] | None = None):
    """Start a run for a stored Test via Engine API."""
    body = body or {}
    engine_base = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")
    headers: Dict[str, str] = {}
    try:
        if request.headers.get("X-API-Key"):
            headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
        pass
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{engine_base}/tests/{test_id}/runs",
                json=body,
                headers=headers or None,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal run test error: {e!s}")
    run_id = data.get("run_id")
    return {"runId": run_id, "engine": data}


@router.post("/nl-run", status_code=201)
def nl_run(body: Dict[str, Any] | None = None):
    body = body or {}
    url = (body.get("url") or "").strip()
    steps_text = body.get("stepsText") or body.get("steps") or ""
    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=400, detail="'url' is required")
    steps = parse_steps_text(str(steps_text))
    if not steps:
        raise HTTPException(status_code=400, detail="'stepsText' is empty")
    # Build minimal spec
    import time

    spec = {
        "id": body.get("id") or f"nl-{int(time.time())}",
        "suite": body.get("suite") or "default",
        "name": body.get("name") or "nl-run",
        "steps": steps,
    }
    # Enqueue live run via engine queue
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{ENGINE_API_BASE}/queue/runs",
                json={"mode": "live", "url": url, "spec": spec},
            )
            r.raise_for_status()
            job_id = r.json().get("job_id")
            return {"jobId": job_id, "spec": spec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"nl-run enqueue error: {e!s}")

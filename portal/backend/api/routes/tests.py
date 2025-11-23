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
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{engine_base}/tests", json=engine_payload, headers=headers or None)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal create test error: {e!s}")
    test_id = data.get("test_id") or body.get("id")
    return {"testId": test_id, "engine": data}


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
            r = client.post(f"{engine_base}/tests/{test_id}/runs", json=body, headers=headers or None)
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

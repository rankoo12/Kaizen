from typing import Any, Dict

import os
import httpx
from fastapi import APIRouter, HTTPException

# Lazy/safe import of engine parser (portal runs as a separate module)
try:
    from engine.core.parsing.nl_steps import parse_steps_text  # type: ignore
except Exception:
    def parse_steps_text(steps_text: str):
        steps = []
        if isinstance(steps_text, str):
            for raw in steps_text.splitlines():
                line = (raw or "").strip()
                if not line or line.startswith("#"):
                    continue
                steps.append({"text": line})
        return steps

router = APIRouter(prefix="/tests", tags=["tests"])


@router.post("", status_code=201)
def create_test():
    return {"testId": "T-0001"}


ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")


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

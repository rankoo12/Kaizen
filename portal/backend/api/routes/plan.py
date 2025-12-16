from typing import Any, Dict

import os
import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/plan", tags=["plan"])

ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")


@router.post("/preview")
def preview(request: Request, body: Dict[str, Any] | None = None):
  """Proxy LLM plan preview to the Engine API.

  Frontend sends a simple payload:
    { "text": str, "context": { ... } }
  and receives the Engine's response:
    { "plan": [...], "valid": bool, "errors": [...], "model": ... }.
  """
  body = body or {}
  text = body.get("text") or ""
  context = body.get("context") or {}
  if not isinstance(text, str) or not text.strip():
    raise HTTPException(status_code=422, detail="'text' is required")
  payload = {"text": text, "context": context if isinstance(context, dict) else {}}
  headers: Dict[str, str] = {}
  try:
    if request.headers.get("X-API-Key"):
      headers["X-API-Key"] = request.headers["X-API-Key"]
  except Exception:
    headers = {}
  try:
    with httpx.Client(timeout=60.0) as client:
      r = client.post(
        f"{ENGINE_API_BASE}/plan/preview",
        json=payload,
        headers=headers or None,
      )
      r.raise_for_status()
      return r.json()
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"portal plan preview error: {e!s}")

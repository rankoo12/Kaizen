import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/metrics", tags=["metrics"])

ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")


def _client_get(
    client: httpx.Client,
    url: str,
    *,
    params: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
):
  try:
    return client.get(url, params=params, headers=headers or None)
  except TypeError:
    return client.get(url, params=params)


@router.get("/summary")
def get_metrics_summary(request: Request, window: int | None = None):
  """Proxy metrics summary from the Engine API.

  This powers the Insights page cards for healing success rate,
  average resolve time, and fallback usage.
  """
  try:
    params: Dict[str, Any] = {}
    if window is not None:
      params["window"] = int(window)
    headers: Dict[str, str] = {}
    try:
      if request.headers.get("X-API-Key"):
        headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
      pass
    with httpx.Client(timeout=10.0) as client:
      r = _client_get(
        client,
        f"{ENGINE_API_BASE}/metrics/summary",
        params=params or None,
        headers=headers or None,
      )
      r.raise_for_status()
      return r.json()
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"portal metrics summary error: {e!s}")

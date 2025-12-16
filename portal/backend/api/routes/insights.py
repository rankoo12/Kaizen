import os
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/insights", tags=["insights"])

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


@router.get("/selectors")
def get_learned_selectors(request: Request, limit: int = 50):
  """Return a lightweight view of learned locator profiles.

  This is a thin adapter over the Engine's /api/profiles endpoint, which is
  backed by the locator_profiles table in Postgres. It normalizes the shape
  into the selectors model expected by the portal frontend.
  """
  try:
    headers: Dict[str, str] = {}
    try:
      if request.headers.get("X-API-Key"):
        headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
      pass
    with httpx.Client(timeout=10.0) as client:
      r = _client_get(
        client,
        f"{ENGINE_API_BASE}/profiles",
        params={"limit": int(limit)},
        headers=headers or None,
      )
      r.raise_for_status()
      payload = r.json()
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"portal selectors error: {e!s}")

  out: List[Dict[str, Any]] = []
  for prof in (payload.get("profiles") or []):
    selector = prof.get("selector") or {}
    target_sig = prof.get("target_signature") or {}
    primary_locator = ""
    try:
      # Prefer CSS value; fall back to generic string repr
      if isinstance(selector, dict) and selector.get("value"):
        primary_locator = str(selector.get("value"))
      else:
        primary_locator = str(selector)
    except Exception:
      primary_locator = ""
    query_text = ""
    try:
      query_text = str(target_sig.get("query") or "")
    except Exception:
      query_text = ""
    hits = int(prof.get("hits") or 0)
    last_seen_raw = prof.get("last_seen")
    last_seen_ts: float | None = None
    # last_seen is currently a stringified timestamp in the Engine API; leave
    # it as-is for now and let the frontend treat None as "—".
    try:
      if isinstance(last_seen_raw, (int, float)):
        last_seen_ts = float(last_seen_raw)
    except Exception:
      last_seen_ts = None

    out.append(
      {
        "query_text": query_text or "(unknown query)",
        "primary_locator": primary_locator or "(selector)",
        "confidence": 1.0,  # placeholder; detailed selector confidence TBD
        "times_used": hits,
        "last_seen_at": last_seen_ts,
      }
    )

  return {"selectors": out}


@router.get("/flaky-tests")
def get_flaky_tests(request: Request, window: int | None = None, limit: int = 20):
  """Return a simple list of potentially flaky tests.

  This implementation is intentionally lightweight: it looks at the Engine's
  /api/runs rollup and computes a per-test failure rate within the current
  reporter window. For more advanced analysis, use Grafana dashboards fed
  from the Postgres runs table.
  """
  try:
    headers: Dict[str, str] = {}
    try:
      if request.headers.get("X-API-Key"):
        headers["X-API-Key"] = request.headers["X-API-Key"]
    except Exception:
      pass
    params: Dict[str, Any] = {"limit": 300}
    with httpx.Client(timeout=10.0) as client:
      r = _client_get(
        client,
        f"{ENGINE_API_BASE}/runs",
        params=params,
        headers=headers or None,
      )
      r.raise_for_status()
      payload = r.json()
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"portal flaky tests error: {e!s}")

  runs: List[Dict[str, Any]] = list(payload.get("runs") or [])
  stats_by_test: Dict[str, Dict[str, Any]] = {}

  for r in runs:
    stats = r.get("stats") or {}
    fields = r.get("fields") or {}
    test_id = fields.get("test_id") or r.get("test_id")
    if not test_id:
      continue
    test_id = str(test_id)
    total = int(stats.get("total") or 0)
    failed = int(stats.get("failed") or 0)
    started = r.get("started")
    rec = stats_by_test.setdefault(
      test_id,
      {
        "test_id": test_id,
        "test_name": fields.get("test_name") or test_id,
        "total": 0,
        "failed": 0,
        "recent_failures": 0,
        "last_failed_at": None,
      },
    )
    rec["total"] += total or 1
    rec["failed"] += failed
    if failed > 0:
      rec["recent_failures"] += 1
      try:
        if started is not None:
          ts = float(started)
          if rec["last_failed_at"] is None or ts > rec["last_failed_at"]:
            rec["last_failed_at"] = ts
      except Exception:
        pass

  out: List[Dict[str, Any]] = []
  for rec in stats_by_test.values():
    total = rec.get("total") or 0
    failed = rec.get("failed") or 0
    if total <= 0:
      continue
    rate = float(failed) / float(total)
    if rate <= 0.0:
      continue
    out.append(
      {
        "test_id": rec["test_id"],
        "test_name": rec.get("test_name"),
        "flakiness_rate": rate,
        "recent_failures": rec.get("recent_failures", 0),
        "last_failed_at": rec.get("last_failed_at"),
      }
    )

  out.sort(key=lambda t: t["flakiness_rate"], reverse=True)
  return {"tests": out[: max(1, int(limit))]}

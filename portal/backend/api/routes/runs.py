import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter(prefix="/runs", tags=["runs"])


ENGINE_API_BASE = os.environ.get("ENGINE_API_BASE", "http://engine-api:8080/api")
ENGINE_API_TIMEOUT_SECONDS = float(os.environ.get("PORTAL_ENGINE_TIMEOUT_SECONDS", "3.0") or 3.0)
PORTAL_DB_TIMEOUT_SECONDS = float(os.environ.get("PORTAL_DB_TIMEOUT_SECONDS", "3.0") or 3.0)


def _engine_api_bases() -> list[str]:
    """Return candidate Engine API base URLs, preferring configured values."""
    bases: list[str] = []
    primary = str(ENGINE_API_BASE).strip()
    if primary:
        bases.append(primary)
    fallback = os.environ.get("ENGINE_API_FALLBACK_BASE")
    if isinstance(fallback, str) and fallback.strip():
        bases.append(fallback.strip())
    # Common local dev fallbacks when docker DNS is unavailable
    if "engine-api" in primary:
        bases.extend(["http://localhost:8080/api", "http://127.0.0.1:8080/api"])
    # De-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _candidate_run_urls(base: str) -> list[str]:
    """Return possible /runs URLs for a given base (with/without /api)."""
    b = str(base or "").strip().rstrip("/")
    if not b:
        return []
    urls = [f"{b}/runs"]
    if b.endswith("/api"):
        urls.append(f"{b[:-4]}/runs")
    else:
        urls.append(f"{b}/api/runs")
    # de-dup
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _pg_dsn() -> str | None:
    dsn = os.environ.get("KAIZEN_PG_DSN") or os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
    if isinstance(dsn, str) and dsn.strip():
        return dsn.strip()
    return None


def _db_list_runs(
    *,
    limit: int,
    offset: int,
    since: float | None,
) -> Dict[str, Any] | None:
    dsn = _pg_dsn()
    if not dsn:
        return None
    try:
        import psycopg
    except Exception:
        return None
    try:
        where = []
        args: list[Any] = []
        if since is not None:
            where.append("started_at >= to_timestamp(%s)")
            args.append(float(since))
        sql = (
            "SELECT run_id, test_id, extract(epoch from started_at) as started, "
            "extract(epoch from finished_at) as finished, stats "
            "FROM runs"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY started_at DESC LIMIT %s OFFSET %s"
        args.extend([int(limit), int(offset)])
        rows: list[dict] = []
        with psycopg.connect(
            dsn, autocommit=True, connect_timeout=PORTAL_DB_TIMEOUT_SECONDS
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(args))
                for row in cur.fetchall():
                    run_id = row[0]
                    test_id = row[1]
                    started = float(row[2]) if row[2] is not None else None
                    finished = float(row[3]) if row[3] is not None else None
                    stats = row[4] or {}
                    duration = (finished - started) if finished is not None and started is not None else None
                    rows.append(
                        {
                            "run_id": run_id,
                            "mode": None,
                            "started": started,
                            "finished": finished,
                            "duration": duration,
                            "stats": stats,
                            "by_tool": {},
                            "fields": {"test_id": test_id} if test_id else {},
                        }
                    )
        return {"runs": rows, "total": len(rows), "offset": offset, "limit": limit}
    except Exception:
        return None


def _client_get(client: httpx.Client, url: str, *, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None):
    """Compatibility wrapper for httpx.Client.get.

    Some tests patch httpx.Client with fakes that do not accept the
    "headers" keyword argument. This helper attempts the full call
    signature first, and on TypeError falls back to a minimal call
    without headers so tests remain deterministic.
    """
    try:
        return client.get(url, params=params, headers=headers or None)
    except TypeError:
        return client.get(url, params=params)


@router.post("")
def create_run(request: Request, body: Dict[str, Any] | None = None):
    body = body or {}
    # If a suite spec is provided, ensure it is stored first
    try:
        spec = body.get("spec")
        suite_id = body.get("suite_id") or (spec or {}).get("id")
        if spec and not suite_id:
            # allow name-based id fallback
            suite_id = spec.get("name")
        if spec:
            headers = {}
            try:
                if request.headers.get("X-API-Key"):
                    headers["X-API-Key"] = request.headers["X-API-Key"]
            except Exception:
                pass
            with httpx.Client(timeout=10.0) as client:
                client.post(f"{ENGINE_API_BASE}/suites", json={"spec": spec, "id": suite_id}, headers=headers or None)
        # Enqueue job for runner to execute
        enqueue_payload = {
            k: v
            for k, v in body.items()
            if k in ("spec", "mode", "html", "html_path", "url", "snapshot", "snapshot_path")
        }
        if not enqueue_payload.get("spec") and suite_id:
            # retrieve spec to enqueue by value
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{ENGINE_API_BASE}/suites/{suite_id}")
                if r.status_code == 200:
                    enqueue_payload["spec"] = r.json().get("spec")
        headers = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{ENGINE_API_BASE}/queue/runs", json=enqueue_payload, headers=headers or None)
            r.raise_for_status()
            job_id = r.json().get("job_id")
            print(f"[portal] enqueued job job_id={job_id}")
        return {"jobId": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal run enqueue error: {e!s}")


@router.get("")
def list_runs(request: Request, mode: str | None = None, limit: int | None = None, offset: int | None = None, since: float | None = None):
    # Proxy to engine API /api/runs with query params
    try:
        q: Dict[str, Any] = {}
        if mode:
            q["mode"] = mode
        if limit is not None:
            q["limit"] = int(limit)
        if offset is not None:
            q["offset"] = int(offset)
        if since is not None:
            q["since"] = float(since)
        headers = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        last_err: Exception | None = None
        for base in _engine_api_bases():
            for url in _candidate_run_urls(base):
                try:
                    with httpx.Client(timeout=ENGINE_API_TIMEOUT_SECONDS) as client:
                        r = _client_get(client, url, params=q, headers=headers or None)
                        r.raise_for_status()
                        return r.json()
                except Exception as e:
                    last_err = e
                    # Quick DB fallback if available so UI doesn't hang on retries.
                    db_payload = _db_list_runs(
                        limit=int(limit or 50),
                        offset=int(offset or 0),
                        since=since,
                    )
                    if isinstance(db_payload, dict) and (db_payload.get("runs") or []):
                        return db_payload
                    continue
        # DB fallback when engine API is unreachable
        db_payload = _db_list_runs(
            limit=int(limit or 50),
            offset=int(offset or 0),
            since=since,
        )
        if isinstance(db_payload, dict):
            return db_payload
        raise HTTPException(status_code=500, detail=f"portal runs list error: {last_err!s}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal runs list error: {e!s}")


@router.get("/{job_id}")
def get_run(request: Request, job_id: str):
    # Reflect queued/running and return run stats if available
    try:
        headers = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=10.0) as client:
            st = _client_get(client, f"{ENGINE_API_BASE}/queue/state", headers=headers or None).json()
            running = st.get("running") or []
            matched_running = None
            for r in running:
                if str(r.get("job_id")) == str(job_id):
                    matched_running = r
                    break
            if matched_running is not None:
                run_id = matched_running.get("run_id")
                if run_id:
                    data = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}", headers=headers or None).json()
                    return {"jobId": job_id, "runId": run_id, "status": data.get("status"), "stats": data.get("stats", {}), "byTool": data.get("by_tool", {})}
                # If job is running but run_id not yet assigned, reflect running state
                return {"jobId": job_id, "status": "running"}
            # if still queued
            queued = st.get("queued") or []
            for q in queued:
                if str(q.get("job_id")) == str(job_id):
                    return {"jobId": job_id, "status": "queued"}
            # fallback: recently completed lookup
            comp = _client_get(client, f"{ENGINE_API_BASE}/queue/completed/{job_id}", headers=headers or None).json().get("job")
            if comp and comp.get("run_id"):
                run_id = comp.get("run_id")
                data = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}", headers=headers or None).json()
                return {"jobId": job_id, "runId": run_id, "status": data.get("status"), "stats": data.get("stats", {}), "byTool": data.get("by_tool", {})}
            return {"jobId": job_id, "status": "unknown"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal run status error: {e!s}")


@router.get("/{run_id}/details")
def get_run_details(request: Request, run_id: str):
    """Proxy detailed run view (including action timeline) from Engine API."""
    try:
        headers: Dict[str, str] = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=10.0) as client:
            r = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}/details", headers=headers or None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal run details error: {e!s}")


@router.get("/{run_id}/annotations")
def get_run_annotations(request: Request, run_id: str):
    """Proxy per-action annotations for a run from Engine API."""
    try:
        headers: Dict[str, str] = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=10.0) as client:
            r = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}/annotations", headers=headers or None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal run annotations error: {e!s}")


@router.post("/{run_id}/annotations")
def add_run_annotation(request: Request, run_id: str, body: Dict[str, Any] | None = None):
    """Proxy creation/update of per-action annotations to the Engine API."""
    body = body or {}
    try:
        headers: Dict[str, str] = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{ENGINE_API_BASE}/runs/{run_id}/annotations", json=body, headers=headers or None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal add annotation error: {e!s}")


@router.get("/{run_id}/artifacts")
def get_run_artifacts(request: Request, run_id: str):
    """Proxy artifacts list from Engine API.

    Returns whatever the Engine API returns (JSON with items)."""
    try:
        headers = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=20.0) as client:
            r = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}/artifacts", headers=headers or None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal artifacts error: {e!s}")


@router.get("/{run_id}/artifacts/{name:path}")
def get_run_artifact_blob(request: Request, run_id: str, name: str):
    """Stream a single artifact (screenshot/log/etc) via the portal.

    Mirrors content-type and bytes from the Engine API.
    """
    try:
        headers = {}
        try:
            if request.headers.get("X-API-Key"):
                headers["X-API-Key"] = request.headers["X-API-Key"]
        except Exception:
            pass
        with httpx.Client(timeout=None) as client:
            r = _client_get(client, f"{ENGINE_API_BASE}/runs/{run_id}/artifacts/{name}", headers=headers or None)
            r.raise_for_status()
            ct = r.headers.get("content-type", "application/octet-stream")
            return Response(content=r.content, media_type=ct)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"portal artifact fetch error: {e!s}")

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query

from engine.core.config.container import Container


router = APIRouter(prefix="/api", tags=["profiles"])


@router.get("/profiles")
def list_profiles(tool: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200)):
    """List recent locator profiles (best-effort; requires Postgres backend)."""
    c = Container()
    st = c.storage()
    if not hasattr(st, "_conn"):
        return {"profiles": []}
    sql = "SELECT tool, target_signature, selector, hits, last_seen FROM locator_profiles"
    args: list[Any] = []
    if tool:
        sql += " WHERE tool=%s"
        args.append(tool)
    sql += " ORDER BY hits DESC, last_seen DESC LIMIT %s"
    args.append(limit)
    rows: list[dict] = []
    try:
        with st._conn() as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:
                cur.execute(sql, tuple(args))
                for r in cur.fetchall():
                    rows.append({
                        "tool": r[0],
                        "target_signature": r[1],
                        "selector": r[2],
                        "hits": r[3],
                        "last_seen": str(r[4]),
                    })
    except Exception:
        rows = []
    return {"profiles": rows}


@router.post("/profiles/lookup")
def lookup_profile(body: Dict[str, Any]):
    tool = (body or {}).get("tool")
    sig = (body or {}).get("target_signature") or {}
    domain = (body or {}).get("domain")
    if not tool:
        raise HTTPException(status_code=400, detail="'tool' is required")
    c = Container()
    st = c.storage()
    find = getattr(st, "find_locator_profile", None)
    if not callable(find):
        return {"profile": None}
    prof = find(domain=domain, tool=str(tool), target_signature=dict(sig))
    return {"profile": prof}

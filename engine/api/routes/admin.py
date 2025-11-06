from __future__ import annotations

from fastapi import APIRouter

from engine.core.config.container import Container


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/db/init")
def db_init():
    c = Container()
    st = c.storage()
    fn = getattr(st, "_ensure_schema", None)
    if callable(fn):
        try:
            fn()
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True}


@router.get("/db/tables")
def db_tables():
    c = Container()
    st = c.storage()
    if not hasattr(st, "_conn"):
        return {"tables": []}
    names = []
    try:
        with st._conn() as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2"
                )
                for r in cur.fetchall():
                    names.append(f"{r[0]}.{r[1]}")
    except Exception:
        names = []
    return {"tables": names}


@router.post("/tenants")
def create_tenant(body: dict):
    tid = (body or {}).get("tenant_id")
    name = (body or {}).get("name")
    if not isinstance(tid, str) or not tid:
        return {"ok": False, "error": "tenant_id required"}
    st = Container().storage()
    fn = getattr(st, "create_tenant", None)
    if callable(fn):
        try:
            fn(tid, name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "storage_missing"}


@router.post("/api-keys")
def create_api_key(body: dict):
    tid = (body or {}).get("tenant_id")
    key = (body or {}).get("api_key")
    if not isinstance(tid, str) or not tid or not isinstance(key, str) or not key:
        return {"ok": False, "error": "tenant_id and api_key required"}
    st = Container().storage()
    fn = getattr(st, "create_api_key", None)
    if callable(fn):
        try:
            fn(tid, key)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "storage_missing"}

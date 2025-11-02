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

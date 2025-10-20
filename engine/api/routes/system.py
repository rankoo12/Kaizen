from fastapi import APIRouter, Depends
from engine.core.config.settings import Settings, get_settings

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/version")
def version(settings: Settings = Depends(get_settings)):
    return {"version": settings.VERSION, "git_sha": settings.GIT_SHA}

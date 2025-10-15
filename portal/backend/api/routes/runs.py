from fastapi import APIRouter

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("")
def create_run():
    return {"runId": "R-0001"}


@router.get("/{run_id}")
def get_run(run_id: str):
    return {"status": "queued", "startedAt": None, "finishedAt": None}

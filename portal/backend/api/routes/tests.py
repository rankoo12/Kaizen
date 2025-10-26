from fastapi import APIRouter

router = APIRouter(prefix="/tests", tags=["tests"])


@router.post("", status_code=201)
def create_test():
    return {"testId": "T-0001"}

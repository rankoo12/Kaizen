from fastapi import APIRouter
from ..schemas import TestSpec  # create when needed (pydantic)

router = APIRouter(prefix="/tests", tags=["tests"])


@router.post("", status_code=201)
def create_test():
    return {"testId": "T-0001"}

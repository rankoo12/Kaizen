# engine/api/routes/metrics.py
from fastapi import APIRouter
from engine.core.metrics.collector import metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics():
    return metrics.as_dict()

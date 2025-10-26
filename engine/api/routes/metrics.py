# engine/api/routes/metrics.py
from fastapi import APIRouter, Query
from engine.core.metrics.collector import metrics
import engine.core.reporting.reporter as reporter_mod

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics():
    return metrics.as_dict()


@router.get("/metrics/runs")
def get_runs_metrics(window: int | None = Query(default=None, ge=1)):
    data = reporter_mod.RUN_REPORTER.rollups(window)
    data["metrics_schema"] = 1
    # sanity clamps
    data["heal_attempts"] = max(0, int(data.get("heal_attempts", 0) or 0))
    data["heal_successes"] = max(0, int(data.get("heal_successes", 0) or 0))
    try:
        hr = float(data.get("healed_rate", 0.0) or 0.0)
    except Exception:
        hr = 0.0
    data["healed_rate"] = max(0.0, min(1.0, hr))
    return data


@router.get("/metrics/summary")
def get_metrics_summary(window: int | None = Query(default=None, ge=1)):
    file_stats = metrics.as_dict()
    runs_stats = reporter_mod.RUN_REPORTER.rollups(window)
    # Merge into a single dashboard payload
    summary = {**file_stats, **runs_stats}
    summary["metrics_schema"] = 1
    try:
        hr = float(summary.get("healed_rate", 0.0) or 0.0)
    except Exception:
        hr = 0.0
    summary["healed_rate"] = max(0.0, min(1.0, hr))
    return summary

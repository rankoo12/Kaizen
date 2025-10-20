import json
import time
from pathlib import Path
from threading import RLock
from typing import Dict

from engine.core.config.settings import settings


class MetricsCollector:
    """Lightweight metrics with simple JSON persistence (process-safe, not multi-host)."""

    def __init__(self, file_path: Path) -> None:
        print(f"DIR : {file_path}")
        self.file_path = file_path
        self._lock = RLock()
        self.runs_total = 0
        self.runs_failed = 0
        self.total_duration = 0.0
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        print(f"DIR : {self.file_path}")
        try:
            if self.file_path.exists():
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                self.runs_total = int(data.get("runs_total", 0))
                self.runs_failed = int(data.get("runs_failed", 0))
                self.total_duration = float(data.get("total_duration", 0.0))
        except Exception:
            # corrupt or unreadable -> start fresh
            self.runs_total = 0
            self.runs_failed = 0
            self.total_duration = 0.0

    def _save(self) -> None:
        tmp = self.file_path.with_suffix(".json.tmp")
        payload = {
            "runs_total": self.runs_total,
            "runs_failed": self.runs_failed,
            "total_duration": self.total_duration,
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.file_path)

    # ---------- public API ----------
    def record_run(self, success: bool, duration: float) -> None:
        with self._lock:
            self.runs_total += 1
            if not success:
                self.runs_failed += 1
            self.total_duration += duration
            self._save()

    def as_dict(self) -> Dict[str, float]:
        with self._lock:
            # Refresh from disk so values reflect updates from other processes
            # (e.g., CLI runs writing to logs/metrics.json while API is running)
            self._load()
            avg = (self.total_duration / self.runs_total) if self.runs_total else 0.0
            return {
                "runs_total": self.runs_total,
                "runs_failed": self.runs_failed,
                "average_duration": avg,
            }


# global singleton persisted under logs/metrics.json
metrics_path = settings.LOGS_DIR / "metrics.json"
print(f"DIR : {metrics_path}")
metrics_path.parent.mkdir(parents=True, exist_ok=True)
metrics = MetricsCollector(metrics_path)


def time_run(func):
    """Decorator to measure duration and update metrics (persisted to logs/metrics.json)."""

    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        success = True
        try:
            return func(*args, **kwargs)
        except Exception:
            success = False
            raise
        finally:
            duration = time.perf_counter() - start
            metrics.record_run(success, duration)

    return wrapper

from __future__ import annotations
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import time
import uuid

from engine.core.config.settings import settings


class ILog:
    def info(self, msg: str, **kwargs: Any) -> None: ...
    def error(self, msg: str, **kwargs: Any) -> None: ...
    def run_logger(self, run_id: Optional[str] = None) -> "RunJsonlLogger": ...


class RunJsonlLogger:
    """
    Per-run JSONL writer. One line per event:
    { ts, level, run_id, msg, ...context }
    """

    def __init__(self, run_id: Optional[str] = None, logs_dir: Path = None):
        self.run_id = run_id or uuid.uuid4().hex
        self.logs_dir = logs_dir or settings.LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._fp = (self.logs_dir / f"{self.run_id}.jsonl").open("a", encoding="utf-8")

    def _write(self, level: str, msg: str, **kwargs: Any) -> None:
        def normalize(v: Any) -> Any:
            if is_dataclass(v):
                return asdict(v)
            if isinstance(v, Path):
                return str(v)
            return v

        record: Dict[str, Any] = {
            "ts": time.time(),
            "level": level,
            "run_id": self.run_id,
            "msg": msg,
        }
        if kwargs:
            record.update({k: normalize(v) for k, v in kwargs.items()})
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()

    def info(self, msg: str, **kwargs: Any) -> None:
        self._write("INFO", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._write("ERROR", msg, **kwargs)

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass


class JsonlLogger(ILog):
    def __init__(self, logs_dir: Path = None):
        self.logs_dir = logs_dir or settings.LOGS_DIR

    def info(self, msg: str, **kwargs: Any) -> None:
        # fallback: write into a shared background run file (rarely used)
        RunJsonlLogger(logs_dir=self.logs_dir).info(msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        RunJsonlLogger(logs_dir=self.logs_dir).error(msg, **kwargs)

    def run_logger(self, run_id: Optional[str] = None) -> RunJsonlLogger:
        return RunJsonlLogger(run_id=run_id, logs_dir=self.logs_dir)

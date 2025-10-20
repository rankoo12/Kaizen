# engine/core/logging/log.py
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import time
import uuid
import os

from engine.core.config.settings import settings


class ILog:
    def info(self, msg: str, **kwargs: Any) -> None: ...
    def error(self, msg: str, **kwargs: Any) -> None: ...
    def run_logger(self, run_id: Optional[str] = None) -> "RunJsonlLogger": ...


class RunJsonlLogger:
    """
    Per-run JSONL writer. One line per event with a minimal schema:
      { ts, level, run_id, event, ...data }
    (keeps legacy "msg" for backward compatibility)
    """

    def __init__(self, run_id: Optional[str] = None, logs_dir: Path = None):
        self.run_id = run_id or uuid.uuid4().hex
        self.logs_dir = logs_dir or settings.LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # use run-*.jsonl naming for clarity
        self._path = self.logs_dir / f"run-{self.run_id}.jsonl"
        self._fp = self._path.open("a", encoding="utf-8")

        # rotation threshold (bytes) – can be overridden via settings.LOG_MAX_BYTES
        self._max_bytes: int = int(getattr(settings, "LOG_MAX_BYTES", 5_000_000))

    def _maybe_rotate(self) -> None:
        try:
            self._fp.flush()
            size = self._path.stat().st_size if self._path.exists() else 0
            if size >= self._max_bytes:
                self._fp.close()
                rotated = self._path.with_suffix(self._path.suffix + ".1")
                # best-effort single backup
                if rotated.exists():
                    rotated.unlink(missing_ok=True)
                os.replace(self._path, rotated)
                self._fp = self._path.open("a", encoding="utf-8")
        except Exception:
            # never block the run on logging issues
            pass

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
            "event": msg,  # canonical name
            "msg": msg,  # legacy field kept for compatibility
        }
        if kwargs:
            record.update({k: normalize(v) for k, v in kwargs.items()})

        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()
        self._maybe_rotate()

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

"""
Artifacts retention utility.

Prunes local artifact directories by age and/or total size.

Usage:
  python scripts/artifacts_retention.py

Environment:
  KAIZEN_ARTIFACTS_RETENTION_DAYS (int, optional)
  KAIZEN_ARTIFACTS_RETENTION_MAX_BYTES (int, optional)
  KAIZEN_LOGS_DIR (path override, optional)
  KAIZEN_SNAPSHOTS_DIR (path override, optional)
"""

from __future__ import annotations

import os
from pathlib import Path
from engine.core.artifacts.store import prune_fs_artifacts


def env_int(name: str) -> int | None:
    v = os.environ.get(name)
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


def main() -> int:
    from engine.core.config.settings import settings

    logs_dir = Path(os.environ.get("KAIZEN_LOGS_DIR", str(settings.LOGS_DIR)))
    snaps_dir = Path(os.environ.get("KAIZEN_SNAPSHOTS_DIR", str(settings.SNAPSHOTS_DIR)))
    days = env_int("KAIZEN_ARTIFACTS_RETENTION_DAYS")
    maxb = env_int("KAIZEN_ARTIFACTS_RETENTION_MAX_BYTES")
    summary = prune_fs_artifacts([logs_dir, snaps_dir], max_age_days=days, max_total_bytes=maxb)
    print(f"Retention summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

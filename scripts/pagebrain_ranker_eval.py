"""
Evaluate (or baseline) PageBrain ranker on curated datasets,
and report baseline vs model metrics plus lift.
"""
from __future__ import annotations

from pathlib import Path
import json

from engine.eval.pagebrain_ranker import compute_lift

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def main() -> int:
    train_path = REPORTS / "pagebrain_train_export.jsonl"
    dev_path = REPORTS / "pagebrain_dev_export.jsonl"
    metrics = compute_lift(train_path, dev_path)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

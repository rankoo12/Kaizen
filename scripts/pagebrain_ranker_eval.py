""
"Evaluate (or baseline) PageBrain ranker on curated datasets."

from __future__ import annotations

from pathlib import Path
import json

from engine.eval.pagebrain_ranker import train_and_eval

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def main() -> int:
    train_path = REPORTS / "pagebrain_train_export.jsonl"
    dev_path = REPORTS / "pagebrain_dev_export.jsonl"
    metrics = train_and_eval(train_path, dev_path)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

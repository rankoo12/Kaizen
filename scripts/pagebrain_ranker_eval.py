"""
Evaluate (or baseline) PageBrain ranker on curated datasets,
and report baseline vs model metrics plus lift.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.eval.pagebrain_ranker import compute_lift

REPORTS = ROOT / "reports"


def main() -> int:
    train_path = REPORTS / "pagebrain_train_export.jsonl"
    dev_path = REPORTS / "pagebrain_dev_export.jsonl"
    metrics = compute_lift(train_path, dev_path)
    print(json.dumps(metrics, indent=2))
    # If weights are available, persist them as a simple JSON artifact
    # that can be referenced by PAGEBRAIN_MODELS at runtime.
    weights = metrics.get("weights") or {}
    if isinstance(weights, dict) and weights:
        out_path = REPORTS / "pagebrain_model_weights.json"
        try:
            out_path.write_text(json.dumps({"weights": weights}, indent=2), encoding="utf-8")
            print(f"Wrote PageBrain model weights to {out_path}")
        except Exception as e:
            print(f"Warning: failed to write weights file: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

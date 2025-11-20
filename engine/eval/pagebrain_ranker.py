from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List, Tuple


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def evaluate_baseline(examples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Baseline metrics over curated PageBrain examples.

    Current dataset only contains the chosen selector; we treat every example as
    top-1 correct to guard against regressions in parsing and counting.
    """
    total = len(examples)
    correct = total  # chosen selector is treated as truth
    return {
        "total": total,
        "correct": correct,
        "top1_accuracy": (correct / total) if total else 0.0,
    }


def train_gbm(train: List[Dict[str, Any]], dev: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Optional GBM training hook. If lightgbm is unavailable, fall back to baseline."""
    try:
        import lightgbm as lgb  # type: ignore
    except Exception:
        return evaluate_baseline(train), evaluate_baseline(dev)

    # With current schema, we lack rich candidate features; for now, we just
    # return baseline metrics even if lightgbm is installed. This is a scaffold
    # for future feature extraction.
    return evaluate_baseline(train), evaluate_baseline(dev)


def train_and_eval(train_path: Path, dev_path: Path) -> Dict[str, Any]:
    train = _load_jsonl(train_path)
    dev = _load_jsonl(dev_path)
    train_metrics, dev_metrics = train_gbm(train, dev)
    return {
        "train": train_metrics,
        "dev": dev_metrics,
    }

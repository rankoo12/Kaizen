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


def _score_candidate(c: Dict[str, Any]) -> float:
    # Simple heuristic: prefer lower rank, visible/enabled, and shorter selectors
    rank = c.get("rank")
    try:
        rank_score = -float(rank)
    except Exception:
        rank_score = -5.0
    sel = c.get("selector") or {}
    val = sel.get("value")
    try:
        length_score = -float(len(val)) * 0.01 if isinstance(val, str) else 0.0
    except Exception:
        length_score = 0.0
    vis_bonus = 0.5 if c.get("visible", True) else -1.0
    en_bonus = 0.3 if c.get("enabled", True) else -0.5
    return rank_score + length_score + vis_bonus + en_bonus


def evaluate_baseline(examples: List[Dict[str, Any]], k: int = 3) -> Dict[str, Any]:
    """Baseline metrics over curated PageBrain examples with candidates + label."""
    total = len(examples)
    if total == 0:
        return {"total": 0, "correct": 0, "top1_accuracy": 0.0, "topk_accuracy": 0.0, "mrr": 0.0}
    correct_top1 = 0
    correct_topk = 0
    mrr = 0.0
    for ex in examples:
        label = ex.get("label")
        cands = ex.get("candidates") or []
        if label is None or not isinstance(label, int):
            continue
        scored = sorted(
            [(idx, _score_candidate(c)) for idx, c in enumerate(cands)],
            key=lambda t: t[1],
            reverse=True,
        )
        if not scored:
            continue
        ranks = [idx for idx, _ in scored]
        if ranks[0] == label:
            correct_top1 += 1
        if label in ranks[:k]:
            correct_topk += 1
        try:
            rr = 1.0 / (ranks.index(label) + 1)
            mrr += rr
        except Exception:
            pass
    return {
        "total": total,
        "correct": correct_top1,
        "top1_accuracy": correct_top1 / total,
        "topk_accuracy": correct_topk / total,
        "mrr": mrr / total,
    }


def train_gbm(train: List[Dict[str, Any]], dev: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Optional GBM training hook. If lightgbm is unavailable, fall back to baseline."""
    try:
        import lightgbm as lgb  # type: ignore
    except Exception:
        return evaluate_baseline(train), evaluate_baseline(dev)

    # With current schema, we lack extensive features; we still compute baseline.
    return evaluate_baseline(train), evaluate_baseline(dev)


def train_and_eval(train_path: Path, dev_path: Path) -> Dict[str, Any]:
    train = _load_jsonl(train_path)
    dev = _load_jsonl(dev_path)
    train_metrics, dev_metrics = train_gbm(train, dev)
    return {
        "train": train_metrics,
        "dev": dev_metrics,
    }

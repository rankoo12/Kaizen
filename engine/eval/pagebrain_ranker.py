from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List, Tuple

FEATURE_KEYS = [
    "rank",
    "selector_len",
    "has_id",
    "has_class",
    "has_attr",
    "num_desc",
    "visible",
    "enabled",
    "type_is_css",
    "type_is_xpath",
]


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


def _feature_vector(cand: Dict[str, Any]) -> List[float]:
    feats = cand.get("features") or {}
    vec: List[float] = []
    for key in FEATURE_KEYS:
        val = feats.get(key)
        if key == "rank":
            try:
                val = float(cand.get("rank", 0.0))
            except Exception:
                val = 0.0
        if val is None:
            val = feats.get(key) if key in feats else 0.0
        try:
            vec.append(float(val))
        except Exception:
            vec.append(0.0)
    return vec


def _build_dataset(examples: List[Dict[str, Any]]) -> tuple[List[List[float]], List[int], List[Tuple[int, int, int]]]:
    X: List[List[float]] = []
    y: List[int] = []
    bounds: List[Tuple[int, int, int]] = []
    for ex in examples:
        label = ex.get("label")
        cands = ex.get("candidates") or []
        if label is None or not isinstance(label, int):
            continue
        start = len(X)
        for idx, cand in enumerate(cands):
            X.append(_feature_vector(cand))
            y.append(1 if idx == label else 0)
        end = len(X)
        if end > start:
            bounds.append((start, end, label))
    return X, y, bounds


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


def _evaluate_predictions(bounds: List[Tuple[int, int, int]], preds: List[float], k: int = 3) -> Dict[str, Any]:
    total = len(bounds)
    if total == 0:
        return {"total": 0, "correct": 0, "top1_accuracy": 0.0, "topk_accuracy": 0.0, "mrr": 0.0}
    top1 = 0
    topk = 0
    mrr = 0.0
    for start, end, label in bounds:
        seg = preds[start:end]
        order = sorted(range(len(seg)), key=lambda i: seg[i], reverse=True)
        if not order:
            continue
        if order[0] == label:
            top1 += 1
        if label in order[:k]:
            topk += 1
        try:
            mrr += 1.0 / (order.index(label) + 1)
        except Exception:
            pass
    return {
        "total": total,
        "correct": top1,
        "top1_accuracy": top1 / total,
        "topk_accuracy": topk / total,
        "mrr": mrr / total,
    }


def train_gbm(train: List[Dict[str, Any]], dev: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Train a simple GBM ranker when lightgbm is available; fallback to baseline otherwise."""
    train_X, train_y, train_bounds = _build_dataset(train)
    dev_X, dev_y, dev_bounds = _build_dataset(dev)
    if not train_X or not dev_X:
        return evaluate_baseline(train), evaluate_baseline(dev)
    try:
        import lightgbm as lgb  # type: ignore
    except Exception:
        return evaluate_baseline(train), evaluate_baseline(dev)

    train_data = lgb.Dataset(train_X, label=train_y)
    params = {
        "objective": "binary",
        "learning_rate": 0.1,
        "num_leaves": 31,
        "feature_pre_filter": False,
        "verbosity": -1,
    }
    model = lgb.train(params, train_data, num_boost_round=50)
    train_preds = model.predict(train_X)
    dev_preds = model.predict(dev_X)
    return _evaluate_predictions(train_bounds, train_preds), _evaluate_predictions(dev_bounds, dev_preds)


def train_and_eval(train_path: Path, dev_path: Path) -> Dict[str, Any]:
    train = _load_jsonl(train_path)
    dev = _load_jsonl(dev_path)
    train_metrics, dev_metrics = train_gbm(train, dev)
    return {
        "train": train_metrics,
        "dev": dev_metrics,
    }

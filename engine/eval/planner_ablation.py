from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List


PlanFn = Callable[[str], List[str]]


@dataclass
class PlannerExample:
    text: str
    expected_tools: List[str]
    category: str = "generic"


def evaluate_examples(examples: List[PlannerExample], plan_fn: PlanFn) -> Dict[str, Any]:
    """Evaluate a planner against expected tool sequences.

    The plan_fn should return a list of tool names for a given text. We compare
    the prefix of that list to expected_tools.
    """
    total = len(examples)
    correct = 0
    by_cat: Dict[str, Dict[str, Any]] = {}

    for ex in examples:
        pred = plan_fn(ex.text) or []
        ok = pred[: len(ex.expected_tools)] == ex.expected_tools
        if ok:
            correct += 1
        cat = ex.category or "generic"
        bucket = by_cat.setdefault(cat, {"total": 0, "correct": 0, "accuracy": 0.0})
        bucket["total"] += 1
        if ok:
            bucket["correct"] += 1

    for cat, bucket in by_cat.items():
        if bucket["total"]:
            bucket["accuracy"] = bucket["correct"] / bucket["total"]

    acc = (correct / total) if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": acc,
        "by_category": by_cat,
    }

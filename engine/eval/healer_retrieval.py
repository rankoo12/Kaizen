from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from engine.core.healing.selector_healer import DeterministicHealer


@dataclass
class HealerEvalCase:
    case_id: str
    failure: Dict[str, Any]
    context: Dict[str, Any]
    category: str = "generic"
    expect_reason: str | None = None  # e.g., "generalized_css", "stable_id", "retrieval_hit"


def run_healer_case(healer: DeterministicHealer, case: HealerEvalCase) -> Tuple[bool, Dict[str, Any]]:
    """
    Run a single healer evaluation case and return (ok, meta).

    ok is true when the healer produced a primary locator and, if expect_reason
    is set on the case, the healer's reason matches that expectation.
    """
    result = healer.heal(case.failure, case.context)
    meta: Dict[str, Any] = {}
    if not isinstance(result, dict) or not isinstance(result.get("primary"), dict):
        meta["reason"] = None
        meta["ok_primary"] = False
        return False, meta
    primary = result["primary"]
    meta["reason"] = result.get("reason")
    meta["primary"] = primary
    ok = bool(primary.get("value"))
    if case.expect_reason is not None:
        ok = ok and meta.get("reason") == case.expect_reason
    return ok, meta


def aggregate(results: List[Tuple[HealerEvalCase, bool, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Aggregate healer evaluation results into simple metrics.

    Returns:
      - total / passed / failed / success_rate
      - by_category: per-category totals and success_rate
      - by_reason: counts per heal "reason" string
    """
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    summary: Dict[str, Any] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": (passed / total) if total else 0.0,
    }

    by_cat: Dict[str, Dict[str, Any]] = {}
    by_reason: Dict[str, int] = {}
    for case, ok, meta in results:
        cat = getattr(case, "category", "generic") or "generic"
        bucket = by_cat.setdefault(cat, {"total": 0, "passed": 0, "failed": 0, "success_rate": 0.0})
        bucket["total"] += 1
        if ok:
            bucket["passed"] += 1
        bucket["failed"] = bucket["total"] - bucket["passed"]

        reason = meta.get("reason")
        key = str(reason) if reason is not None else "none"
        by_reason[key] = by_reason.get(key, 0) + 1

    for cat, bucket in by_cat.items():
        if bucket["total"]:
            bucket["success_rate"] = bucket["passed"] / bucket["total"]

    if by_cat:
        summary["by_category"] = by_cat
    if by_reason:
        summary["by_reason"] = by_reason
    return summary


def default_corpus() -> List[HealerEvalCase]:
    """
    Deterministic cases that exercise core DeterministicHealer paths
    without requiring a real database or embeddings.
    """
    return [
        # Generalize CSS selector
        HealerEvalCase(
            case_id="css_generalize_button",
            category="css",
            failure={"target": {"css": "button.primary.large"}},
            context={"tool": "click", "domain": "example.com", "tenant_id": None},
            expect_reason="generalized_css",
        ),
        # Stable id attribute
        HealerEvalCase(
            case_id="stable_id_login",
            category="stable_attr",
            failure={"target": {"id": "login-btn"}},
            context={"tool": "click", "domain": "example.com", "tenant_id": None},
            expect_reason="stable_id",
        ),
        # Stable testid attribute
        HealerEvalCase(
            case_id="stable_testid_submit",
            category="stable_attr",
            failure={"target": {"testid": "submit-btn"}},
            context={"tool": "click", "domain": "example.com", "tenant_id": None},
            expect_reason="stable_testid",
        ),
        # Text fallback when no css/id/testid present
        HealerEvalCase(
            case_id="text_fallback_login",
            category="text",
            failure={"target": {"text": "Login"}},
            context={"tool": "click", "domain": "example.com", "tenant_id": None},
            expect_reason="text_fallback",
        ),
    ]

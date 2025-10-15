from typing import Protocol

from ...types.dtos import TargetQuery


class IResolverStrategy(Protocol):
    """Score catalog entries for a query (higher is better)."""

    def score(
        self, query: TargetQuery, catalog: list[dict]
    ) -> list[tuple[dict, float]]: ...


class SemanticStrategy:
    """Heuristic scoring:
    +3 role match
    +2 data-testid match
    +2 id match
    +1 text contains (case-insensitive)
    +0.5 visible
    +0.5 clickable
    """

    def score(
        self, query: TargetQuery, catalog: list[dict]
    ) -> list[tuple[dict, float]]:
        qt = (query.get("text") or "").strip()
        qh = query.get("hints", {}) or {}
        want_role = (qh.get("role") or "").strip().lower()
        want_text = qt.lower()

        scored: list[tuple[dict, float]] = []
        for c in catalog:
            s = 0.0
            role = (c.get("role") or "").lower()
            text = (c.get("text") or "") or (c.get("aria_label") or "")
            cid = c.get("id") or ""
            attrs = c.get("attrs") or {}
            testid = attrs.get("testid") or ""

            if want_role and role == want_role:
                s += 3.0
            if testid and want_text and testid.lower() == want_text:
                s += 2.0
            if cid and want_text and cid.lower() == want_text:
                s += 2.0
            if want_text and text and want_text in str(text).lower():
                s += 1.0
            if c.get("visible") is True:
                s += 0.5
            if c.get("clickable") is True:
                s += 0.5

            scored.append((c, s))

        # highest score first; stable by original order for ties
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

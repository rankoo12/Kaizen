from __future__ import annotations

from typing import List, Tuple

from ...types.dtos import TargetQuery


def _lower(v):
    try:
        return str(v).lower()
    except Exception:
        return ""


class AttributeStrategy:
    """Score candidates by attribute exact/contains matches.

    Weights (approx):
    +4 data-testid exact
    +4 id exact
    +3 name exact
    +2 aria-label contains
    +2 placeholder contains
    +2 value contains for radios/checkboxes
    """

    def score(self, query: TargetQuery, catalog: List[dict]) -> List[Tuple[dict, float]]:
        qt = (query.get("text") or "").strip().lower()
        scored: List[Tuple[dict, float]] = []
        for c in catalog:
            s = 0.0
            attrs = c.get("attrs") or {}
            testid = _lower(attrs.get("testid"))
            cid = _lower(c.get("id"))
            name = _lower(c.get("name"))
            aria = _lower(c.get("aria_label")) or _lower(c.get("ariaLabel"))
            placeholder = _lower(c.get("placeholder"))
            ctype = _lower(c.get("type"))
            val = _lower(c.get("value")) or _lower(c.get("valueAttr"))

            if qt and testid == qt:
                s += 4
            if qt and cid == qt:
                s += 4
            if qt and name == qt:
                s += 3
            if qt and qt in aria:
                s += 2
            if qt and qt in placeholder:
                s += 2
            if qt and c.get("tag") == "input" and ctype in ("radio", "checkbox") and qt in val:
                s += 2

            scored.append((c, s))
        return scored

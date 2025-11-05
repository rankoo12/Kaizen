from __future__ import annotations

from typing import List, Tuple

from ...types.dtos import TargetQuery


def _lower(v):
    try:
        return str(v).lower()
    except Exception:
        return ""


class LabelTextStrategy:
    """Score candidates by label text and inner text.

    Weights:
    +4 any label contains query
    +3 text contains (buttons/links)
    +1 text contains (others)
    """

    def score(self, query: TargetQuery, catalog: List[dict]) -> List[Tuple[dict, float]]:
        qt = (query.get("text") or "").strip().lower()
        scored: List[Tuple[dict, float]] = []
        for c in catalog:
            s = 0.0
            if not qt:
                scored.append((c, s))
                continue
            # labels array may be present
            try:
                labels = [ _lower(x) for x in (c.get("labels") or []) ]
            except Exception:
                labels = []
            if any(qt in lab for lab in labels):
                s += 4
            text = _lower(c.get("text"))
            if text and qt in text:
                if c.get("tag") in ("button", "a"):
                    s += 3
                else:
                    s += 1
            scored.append((c, s))
        return scored

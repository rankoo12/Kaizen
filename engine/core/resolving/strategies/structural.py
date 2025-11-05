from __future__ import annotations

from typing import List, Tuple

from ...types.dtos import TargetQuery


def _lower(v):
    try:
        return str(v).lower()
    except Exception:
        return ""


class StructuralStrategy:
    """Light structural hints without a full DOM tree.

    Weights:
    +2 if query suggests an input type and candidate matches (email/tel/password)
    +1 for generic input when query contains common field words
    +1 role=button when query contains click-y verbs
    """

    def score(self, query: TargetQuery, catalog: List[dict]) -> List[Tuple[dict, float]]:
        qt = _lower((query.get("text") or "").strip())
        scored: List[Tuple[dict, float]] = []
        for c in catalog:
            s = 0.0
            tag = c.get("tag")
            ctype = _lower(c.get("type"))
            role = _lower(c.get("role"))
            if qt:
                if any(w in qt for w in ("email", "e-mail")) and tag == "input" and ctype == "email":
                    s += 2
                if any(w in qt for w in ("phone", "tel", "mobile")) and tag == "input" and ctype == "tel":
                    s += 2
                if any(w in qt for w in ("password", "passcode", "pwd")) and tag == "input" and ctype == "password":
                    s += 2
                if any(w in qt for w in ("field", "input", "textbox")) and tag in ("input", "textarea"):
                    s += 1
                if any(w in qt for w in ("press", "click", "submit")) and (role == "button" or tag in ("button",)):
                    s += 1
            scored.append((c, s))
        return scored

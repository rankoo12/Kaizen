from typing import Protocol, List, Any
from ..types.dtos import TargetQuery, LocatorCandidates, Locator
from .strategies.semantic import SemanticStrategy, IResolverStrategy


class IElementResolver(Protocol):
    """Turn a TargetQuery into ranked LocatorCandidates using strategies."""

    def resolve(
        self, query: TargetQuery, snapshot: "PageSnapshot"
    ) -> LocatorCandidates: ...

    def find(self, target: dict) -> list[Any]: ...


class ElementResolver:
    """Combines strategies; returns primary + fallbacks with a reason and confidence."""

    def __init__(self, strategies: List[IResolverStrategy] | None = None):
        self._strategies: List[IResolverStrategy] = strategies or [SemanticStrategy()]

    def resolve(
        self, query: TargetQuery, snapshot: "PageSnapshot"
    ) -> LocatorCandidates:
        catalog = snapshot.get("candidates", [])
        if not catalog:
            raise ValueError("Empty catalog in snapshot")

        # aggregate scores (for now we just use the first strategy)
        scored = self._strategies[0].score(query, catalog)

        best, best_score = scored[0]
        others = [c for c, _ in scored[1:5]]  # take up to 4 fallbacks

        primary: Locator = self._to_locator(best)
        fallbacks: List[Locator] = [self._to_locator(c) for c in others]

        reason = (
            f"SemanticStrategy score={best_score:.2f} for text='{query.get('text','')}'"
        )
        confidence = (
            float(max(best_score, 0.0)) / 7.0
        )  # crude 0..1 scale (7 = max from weights)

        return {
            "primary": primary,
            "fallbacks": fallbacks,
            "confidence": min(confidence, 1.0),
            "reason": reason,
            "bbox": best.get("bbox"),
        }

    @staticmethod
    def _to_locator(candidate: dict) -> Locator:
        # Prefer testid, then id, then role+text fallback
        attrs = candidate.get("attrs") or {}
        if attrs.get("testid"):
            return {"type": "testid", "value": attrs["testid"]}
        if candidate.get("id"):
            return {"type": "id", "value": candidate["id"]}
        # fallback to a rough css by tag + class
        tag = candidate.get("tag") or "*"
        classes = candidate.get("classes") or []
        cls_sel = ".".join([c for c in classes if c])
        css = tag + (("." + cls_sel) if cls_sel else "")
        return {"type": "css", "value": css}

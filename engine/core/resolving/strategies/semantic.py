from typing import Protocol
from ...types.dtos import TargetQuery


class IResolverStrategy(Protocol):
    """Score catalog entries for a query (higher is better)."""

    def score(
        self, query: TargetQuery, catalog: list[dict]
    ) -> list[tuple[dict, float]]: ...


class SemanticStrategy:
    """Role/aria/id/testid/text heuristic. Placeholder (no logic yet)."""

    def score(
        self, query: TargetQuery, catalog: list[dict]
    ) -> list[tuple[dict, float]]:
        return []

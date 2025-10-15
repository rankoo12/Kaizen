from typing import Protocol
from ..types.dtos import TargetQuery, LocatorCandidates


class IElementResolver(Protocol):
    """Turn a TargetQuery into ranked LocatorCandidates using strategies."""

    def resolve(
        self, query: TargetQuery, snapshot: "PageSnapshot"
    ) -> LocatorCandidates: ...

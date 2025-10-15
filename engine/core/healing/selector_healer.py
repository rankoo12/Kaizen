from typing import Protocol, Optional
from ..types.dtos import LocatorCandidates


class ISelectorHealer(Protocol):
    """Attempt to recover from a failed locator resolution/interaction."""

    def heal(self, failure: dict, context: dict) -> Optional[LocatorCandidates]: ...

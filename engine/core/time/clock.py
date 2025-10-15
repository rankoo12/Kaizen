from typing import Protocol
from datetime import datetime


class IClock(Protocol):
    """Deterministic time source for tests."""

    def now(self) -> datetime: ...

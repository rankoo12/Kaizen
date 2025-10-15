from typing import Protocol
from pydantic import BaseModel


class StepPlan(BaseModel):
    target_query: dict  # minimal schema; validated upstream


class IPlanner(Protocol):
    def plan(self, step_text: str) -> StepPlan: ...


class IResolveSnapshot(Protocol):
    def __call__(
        self,
        *,
        html: str | None = None,
        snapshot_path: str | None = None,
        target_query: dict
    ) -> dict: ...

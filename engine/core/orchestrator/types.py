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
        plan: "StepPlan",
        html_path: str | None = None,
        tolerance: float,
        healer_depth: int,
    ) -> dict: ...

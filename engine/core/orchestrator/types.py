from typing import Protocol, List, Any
from pydantic import BaseModel

# Shared engine types
from engine.core.types.ontology import ToolCall
from engine.core.commands.action_handler import ExecCtx, StepResult


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


# A validated execution plan is a list of ToolCalls
Plan = List[ToolCall]


class IPlanExecutor(Protocol):
    """Execute a validated plan deterministically and return per-call results."""

    def execute(self, plan: "Plan", *, ctx: ExecCtx) -> List[StepResult]: ...


class IOrchestrator(Protocol):
    """High-level coordinator for running specs in snapshot or live mode."""

    def run_snapshot(
        self,
        spec: Any,
        *,
        html_path: str | None = None,
        html: str | None = None,
        snapshot_path: str | None = None,
    ) -> str: ...

    def run_live(self, spec: Any, *, url: str | None = None) -> str: ...

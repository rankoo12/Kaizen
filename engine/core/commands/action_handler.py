from typing import Protocol
from ..types.ontology import ToolCall


class ExecCtx:
    """Immutable execution context for a single run.
    Extend later with logger, clock, storage, browser handle, timeouts.
    """

    run_id: str


class StepResult:
    """Result of executing a single tool call."""

    ok: bool = True
    reason: str | None = None


class IActionHandler(Protocol):
    """Execute a single ToolCall (open/click/type/press/...).

    OCP: each action gets its own handler implementation.
    """

    def execute(self, tool_call: ToolCall, ctx: ExecCtx) -> StepResult: ...

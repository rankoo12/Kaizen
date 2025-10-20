from datetime import datetime, timedelta

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult
from engine.core.orchestrator import reasons as R


class FakeClock:
    def __init__(self, start: datetime | None = None, step_ms: int = 0):
        self.now_val = start or datetime(2025, 1, 1)
        self.step = timedelta(milliseconds=step_ms)

    def now(self) -> datetime:
        t = self.now_val
        self.now_val = self.now_val + self.step
        return t


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_timeout_resolve_when_no_single_candidate_within_deadline():
    class Resolver:
        def find(self, target: dict):
            # Always returns zero candidates
            return []

    ex = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver(), clock=FakeClock(step_ms=50))
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]

    res = ex.execute(plan, ctx=ExecCtx(run_id="r", timeout_ms=100))
    assert res[0].ok is False and res[0].reason == R.TIMEOUT_RESOLVE


def test_resolve_succeeds_before_timeout():
    class Resolver:
        def __init__(self):
            self.calls = 0

        def find(self, target: dict):
            self.calls += 1
            # First call: zero; second: single candidate
            if self.calls < 2:
                return []
            return [{"css": "#login", "visible": True, "enabled": True}]

    ex = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver(), clock=FakeClock(step_ms=10))
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]

    res = ex.execute(plan, ctx=ExecCtx(run_id="r", timeout_ms=1000))
    assert res[0].ok is True


def test_click_safety_not_visible_and_not_enabled():
    class Resolver:
        def __init__(self, cand):
            self.cand = cand

        def find(self, target: dict):
            return [self.cand]

    # Not visible
    ex1 = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver({"css": "#login", "visible": False, "enabled": True}))
    res1 = ex1.execute([{"tool": "click", "args": {"target": {"css": "#login"}}}], ctx=ExecCtx(run_id="r"))
    assert res1[0].ok is False and res1[0].reason == R.NOT_VISIBLE

    # Visible but not enabled
    ex2 = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver({"css": "#login", "visible": True, "enabled": False}))
    res2 = ex2.execute([{"tool": "click", "args": {"target": {"css": "#login"}}}], ctx=ExecCtx(run_id="r"))
    assert res2[0].ok is False and res2[0].reason == R.NOT_ENABLED

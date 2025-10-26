from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult
from engine.core.healing.selector_healer import ISelectorHealer, DeterministicHealer
from engine.core.orchestrator import reasons as R


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_healer_recovers_when_enabled_on_zero_candidates():
    class Resolver:
        def find(self, target: dict):
            return []

    # Enable healing via settings shim
    class _S:
        HEALER_ENABLED = True

    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()}, resolver=Resolver(), settings=_S(), healer=DeterministicHealer()
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True


def test_healer_not_enabled_keeps_failure():
    class Resolver:
        def find(self, target: dict):
            return []

    ex = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver())
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is False and res[0].reason in (R.RESOLVE_ZERO, R.RESOLVE_MULTI)


def test_healer_failure_propagates():
    class Resolver:
        def find(self, target: dict):
            return []

    class NoopHealer(ISelectorHealer):
        def heal(self, failure: dict, context: dict):
            return None

    class _S:
        HEALER_ENABLED = True

    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()}, resolver=Resolver(), healer=NoopHealer(), settings=_S()
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is False and res[0].reason in (R.RESOLVE_ZERO, R.TIMEOUT_RESOLVE, R.RESOLVER_NO_FIND)

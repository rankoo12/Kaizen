from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


class CaptureReporter:
    def __init__(self):
        self.steps = []

    def on_step(self, payload: dict):
        self.steps.append(payload)

    def on_run_start(self, *a, **k):
        pass

    def on_run_finish(self, *a, **k):
        pass

    def on_finish(self, *a, **k):
        pass


def test_per_step_healed_flags_emitted_when_enabled():
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        REPORT_STEP_HEAL_FLAGS = True

    from engine.core.healing.selector_healer import DeterministicHealer

    rep = CaptureReporter()
    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        healer=DeterministicHealer(),
        reporter=rep,
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True
    assert rep.steps and rep.steps[0].get("healed") is True
    assert rep.steps[0].get("healer") in ("deterministic", "llm")
    assert 0.0 <= rep.steps[0].get("confidence", 0.0) <= 1.0


def test_per_step_flags_absent_when_disabled():
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        REPORT_STEP_HEAL_FLAGS = False

    from engine.core.healing.selector_healer import DeterministicHealer

    rep = CaptureReporter()
    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        healer=DeterministicHealer(),
        reporter=rep,
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True
    # healed flags should be absent when disabled
    assert rep.steps and "healed" not in rep.steps[0]

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_healer_generalizes_css_when_find_returns_zero():
    # Resolver that returns no candidates to trigger healing
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        REPORT_STEP_HEAL_FLAGS = True

    from engine.core.healing.selector_healer import DeterministicHealer

    rep = type("_R", (), {"steps": [], "on_step": lambda self, p: self.steps.append(p),
                           "on_run_start": lambda *a, **k: None,
                           "on_run_finish": lambda *a, **k: None,
                           "on_finish": lambda *a, **k: None})()

    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        healer=DeterministicHealer(),
        reporter=rep,
    )
    # CSS contains combinators/pseudo; healer should generalize to a stable base
    plan = [{"tool": "click", "args": {"target": {"css": "button.primary:hover"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True
    assert rep.steps and rep.steps[0].get("healed") is True
    assert rep.steps[0].get("reason") in ("generalized_css", "text_fallback", None)

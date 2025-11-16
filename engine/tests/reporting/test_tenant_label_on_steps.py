from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_step_payload_includes_tenant_when_storage_resolves():
    # Fake storage that returns tenant for the run
    class _Storage:
        def get_run(self, run_id: str):
            return {"run_id": run_id, "tenant_id": "t1"}

    # Resolver returns a single candidate so execute passes
    class _Resolver:
        def find(self, target: dict):
            return [{"type": "css", "value": "#login", "visible": True, "enabled": True}]

    # Capture reporter
    class _Rep:
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

    rep = _Rep()
    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=_Resolver(),
        reporter=rep,
        storage=_Storage(),
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="run-xyz"))
    assert res and res[0].ok is True
    assert rep.steps and rep.steps[0].get("tenant_id") == "t1"

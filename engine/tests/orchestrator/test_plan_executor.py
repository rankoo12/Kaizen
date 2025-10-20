from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class _FakeLog:
    def __init__(self):
        self.events = []

    def info(self, msg: str, **kv):
        self.events.append((msg, kv))

    def error(self, msg: str, **kv):
        self.events.append(("ERROR:" + msg, kv))


class _OpenHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


class _ClickHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        # expect meta.resolved provided by executor
        return StepResult(ok=True, reason=None)


class _Resolver:
    def find(self, target: dict):
        if target.get("text") == "Login":
            return [{"type": "css", "value": "#login", "visible": True, "enabled": True}]
        return []


def test_plan_executor_returns_results_and_logs():
    log = _FakeLog()
    handlers = {"open": _OpenHandler(), "click": _ClickHandler()}
    resolver = _Resolver()
    executor = DeterministicPlanExecutor(handlers=handlers, resolver=resolver, log=log)
    plan = [
        {"tool": "open", "args": {"url": "data:text/html,hello"}},
        {"tool": "click", "args": {"target": {"text": "Login"}}},
    ]
    ctx = ExecCtx(run_id="run-xyz")

    results = executor.execute(plan, ctx=ctx)

    assert len(results) == 2
    assert all(r.ok for r in results)
    # at least one structured log per call
    assert len([e for e in log.events if e[0] == "plan_step"]) == 2

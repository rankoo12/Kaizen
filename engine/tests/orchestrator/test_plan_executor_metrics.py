from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import IActionHandler, StepResult, ExecCtx
from engine.core.orchestrator import reasons as R


class FakeReporter:
    def __init__(self):
        self.metrics = []
        self.steps = []

    def on_metric(self, name: str, tags: dict | None = None):
        self.metrics.append((name, tags or {}))

    def on_step(self, step_run: dict):
        self.steps.append(step_run)


class OkOpen(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_executor_emits_metric_on_success_and_failure():
    reporter = FakeReporter()
    handlers = {"open": OkOpen()}
    ex = DeterministicPlanExecutor(handlers=handlers, reporter=reporter)

    ok_plan = [{"tool": "open", "args": {"url": "data:text/html,ok"}}]
    bad_plan = [{"tool": "open", "args": {"url": "http://blocked"}}]

    ok_res = ex.execute(ok_plan, ctx=ExecCtx(run_id="r"))
    bad_res = ex.execute(bad_plan, ctx=ExecCtx(run_id="r"))

    # Two metric emissions expected
    assert len(reporter.metrics) == 2
    names = [m[0] for m in reporter.metrics]
    assert names == ["executor_step_total", "executor_step_total"]

    tags_ok = reporter.metrics[0][1]
    tags_bad = reporter.metrics[1][1]
    assert tags_ok["tool"] == "open" and tags_ok["ok"] is True and tags_ok["reason"] == "none"
    assert (
        tags_bad["tool"] == "open" and tags_bad["ok"] is False and tags_bad["reason"] == R.URL_SCHEME_NOT_ALLOWED
    )

from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.orchestrator import reasons as R
from engine.core.commands.action_handler import StepResult


class _FakeReporter:
    def __init__(self):
        self.finish = []
        self.start = []

    def on_run_start(self, run_id: str, mode: str, **kv) -> None:
        self.start.append((run_id, mode, kv))

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self.finish.append((run_id, stats))

    def on_finish(self, run_id: str) -> None:
        pass

    def on_step(self, step_run: dict) -> None:
        pass


class _FakeExecutor:
    def __init__(self, results):
        self._results = results

    def execute(self, plan, *, ctx):
        return list(self._results)


class _FakeStorage:
    def start_run(self, test_id):
        return f"run-{test_id}"

    def finish_run(self, run_id):
        pass


class _FakePlanner:
    def plan(self, step_text: str):
        class _P:
            target_query = {"text": step_text}

        return _P()


def test_reasons_breakdown_in_stats():
    reporter = _FakeReporter()
    results = [
        StepResult(ok=True, reason=None),
        StepResult(ok=False, reason=R.TIMEOUT_RESOLVE),
        StepResult(ok=False, reason=R.NOT_VISIBLE),
    ]
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=_FakeExecutor(results),
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=reporter,
    )

    class Spec:
        id = "rb1"
        steps = []

    orch.run_live(Spec())
    assert len(reporter.finish) == 1
    _, stats = reporter.finish[0]
    reasons = stats.get("reasons") or {}
    assert reasons.get("none") == 1
    assert reasons.get(R.TIMEOUT_RESOLVE) == 1
    assert reasons.get(R.NOT_VISIBLE) == 1

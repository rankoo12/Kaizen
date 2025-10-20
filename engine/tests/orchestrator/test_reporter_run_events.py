from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.commands.action_handler import StepResult


class _FakeReporter:
    def __init__(self):
        self.start = []
        self.finish = []
        self.steps = []
        self.metrics = []

    def on_run_start(self, run_id: str, mode: str) -> None:
        self.start.append((run_id, mode))

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self.finish.append((run_id, stats))

    def on_finish(self, run_id: str) -> None:
        pass

    def on_step(self, step_run: dict) -> None:
        self.steps.append(step_run)

    def on_metric(self, name: str, tags: dict | None = None):
        self.metrics.append((name, tags or {}))


class _FakeExecutor:
    def __init__(self, results):
        self._results = results
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
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


def test_reporter_gets_run_events_and_stats():
    reporter = _FakeReporter()
    # one success result
    executor = _FakeExecutor([StepResult(ok=True, reason=None)])
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=executor,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=reporter,
    )

    class Spec:
        id = "rep1"
        steps = []

    run_id = orch.run_live(Spec())
    assert reporter.start == [("run-rep1", "live")]
    assert len(reporter.finish) == 1
    _, stats = reporter.finish[0]
    assert stats["total"] == 1 and stats["passed"] == 1 and stats["failed"] == 0

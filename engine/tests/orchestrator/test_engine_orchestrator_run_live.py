from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.orchestrator.types import IPlanner
from engine.core.commands.action_handler import ExecCtx


class _FakePlanner(IPlanner):
    def plan(self, step_text: str):
        class _StepPlan:
            target_query = {"text": step_text}

        return _StepPlan()


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx: ExecCtx):
        self.calls.append((plan, ctx))
        # Return a list to mimic StepResults
        return []


class _FakeStorage:
    def __init__(self):
        self.started = []
        self.finished = []

    def start_run(self, test_id):
        self.started.append(test_id)
        return f"run-{test_id}"

    def finish_run(self, run_id):
        self.finished.append(run_id)


class _FakeLog:
    def __init__(self):
        self.events = []

    def info(self, msg: str, **kv):
        self.events.append((msg, kv))


def test_engine_orchestrator_run_live_executes_open_first():
    planner = _FakePlanner()
    executor = _FakeExecutor()
    storage = _FakeStorage()
    log = _FakeLog()

    orch = EngineOrchestrator(
        planner=planner,
        plan_executor=executor,
        snapshot_runner=None,  # not used in this test
        storage=storage,
        log=log,
    )

    class Spec:
        id = "demo"
        steps = []

    run_id = orch.run_live(Spec())
    assert run_id == "run-demo"

    # Ensure executor called once with plan having 'open' first
    assert len(executor.calls) == 1
    plan, ctx = executor.calls[0]
    assert isinstance(ctx, ExecCtx)
    assert ctx.run_id == "run-demo"
    assert isinstance(plan, list) and len(plan) >= 1
    assert plan[0].get("tool") == "open"
    assert plan[0].get("args", {}).get("url") == "about:blank"

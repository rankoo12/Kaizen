from engine.core.orchestrator.orchestrator import EngineOrchestrator


class _FakeSnapshotRunner:
    def run(self, spec, html_path=None, html=None, snapshot_path=None):
        return f"run-{getattr(spec, 'id', 'x')}"


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
        return []


class _FakePlanner:
    def plan(self, step_text: str):
        class _P:
            target_query = {"text": step_text}

        return _P()


def test_orchestrator_snapshot_executes_press_steps_via_executor():
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=_FakeExecutor(),
        snapshot_runner=_FakeSnapshotRunner(),
        storage=None,
        log=None,
    )

    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        id = "snap1"
        steps = [Step("press Enter")]

    run_id = orch.run_snapshot(Spec())
    assert run_id == "run-snap1"
    # Ensure executor received an open + press plan
    plan, ctx = orch._executor.calls[0]
    assert plan[0]["tool"] == "open" and plan[0]["args"]["url"] == "about:blank"
    assert plan[1]["tool"] == "press" and plan[1]["args"]["key"].lower() == "enter"

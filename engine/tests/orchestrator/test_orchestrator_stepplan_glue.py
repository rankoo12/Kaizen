from engine.core.orchestrator.orchestrator import EngineOrchestrator


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
        return []


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


def test_orchestrator_converts_simple_steps_to_calls():
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=_FakeExecutor(),
        snapshot_runner=None,  # not used here
        storage=_FakeStorage(),
        log=None,
    )

    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        id = "s1"
        steps = [Step("click login"), Step("type hello"), Step("press Enter")]

    run_id = orch.run_live(Spec())
    assert run_id == "run-s1"

    # Verify the plan
    plan, ctx = orch._executor.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "click" and plan[1]["args"]["target"]["text"] == "login"
    assert plan[2]["tool"] == "type" and plan[2]["args"]["text"] == "hello"
    assert plan[2]["args"]["target"]["text"] == "input"
    assert plan[3]["tool"] == "press" and plan[3]["args"]["key"].lower() == "enter"


def test_orchestrator_prefers_css_when_specific_selector():
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=_FakeExecutor(),
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
    )

    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        id = "s2"
        steps = [Step("click #login"), Step("click .btn-primary"), Step("click Login")]  # mixed

    orch.run_live(Spec())
    plan, _ = orch._executor.calls[0]
    # First two should use css, last should use text
    assert plan[1]["args"]["target"] == {"css": "#login"}
    assert plan[2]["args"]["target"] == {"css": ".btn-primary"}
    assert plan[3]["args"]["target"] == {"text": "Login"}

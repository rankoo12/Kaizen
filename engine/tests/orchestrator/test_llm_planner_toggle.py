import json

from engine.core.orchestrator.orchestrator import EngineOrchestrator


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.payload


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append(plan)
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


class _LLMSettings:
    EXECUTION_PATH = "orchestrator"
    PLANNER_PATH = "llm"


def test_llm_planner_success_path():
    # LLM returns a valid single click
    llm = FakeLLM(json.dumps({"tool": "click", "args": {"target": {"text": "Login"}}}))
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=llm,
        settings=_LLMSettings(),
    )

    class Spec:
        id = "llm1"
        steps = [type("S", (), {"text": "click Login"})()]

    run_id = orch.run_live(Spec())
    assert run_id == "run-llm1"
    plan = ex.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "click"


def test_llm_planner_failure_fallback_to_glue():
    # LLM returns malformed JSON; should fallback to glue mapping
    llm = FakeLLM("not json")
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=llm,
        settings=_LLMSettings(),
    )

    class Spec:
        id = "llm2"
        steps = [type("S", (), {"text": "click Login"})()]

    orch.run_live(Spec())
    plan = ex.calls[0]
    # glue mapping produces a click after open
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "click" and plan[1]["args"]["target"]["text"] == "Login"

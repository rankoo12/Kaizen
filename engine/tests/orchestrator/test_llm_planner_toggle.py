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


class _GlueSettings:
    EXECUTION_PATH = "orchestrator"
    PLANNER_PATH = "glue"


def test_glue_planner_maps_nav_and_scroll():
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=None,
        settings=_GlueSettings(),
    )

    class Spec:
        id = "nav1"
        steps = [
            type("S", (), {"text": "go back"})(),
            type("S", (), {"text": "scroll down a bit"})(),
        ]

    run_id = orch.run_live(Spec())
    assert run_id == "run-nav1"
    plan = ex.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "back"
    assert plan[2]["tool"] == "scroll"


def test_glue_planner_maps_tab_and_download_intents():
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=None,
        settings=_GlueSettings(),
    )

    class Spec2:
        id = "nav2"
        steps = [
            type("S", (), {"text": "open a new tab"})(),
            type("S", (), {"text": "switch to tab 2"})(),
            type("S", (), {"text": "close this tab"})(),
            type("S", (), {"text": "download the report"})(),
        ]

    run_id = orch.run_live(Spec2())
    assert run_id == "run-nav2"
    plan = ex.calls[0]
    assert [p["tool"] for p in plan[:5]] == ["open", "newTab", "switchTab", "closeTab", "download"]


def test_glue_planner_maps_assert_url_and_submit():
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=None,
        settings=_GlueSettings(),
    )

    class Spec3:
        id = "qa1"
        steps = [
            type("S", (), {"text": "check that the URL contains /dashboard"})(),
            type("S", (), {"text": "submit the form"})(),
        ]

    run_id = orch.run_live(Spec3())
    assert run_id == "run-qa1"
    plan = ex.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "assertUrl"
    assert plan[1]["args"]["expected"] == "/dashboard"
    assert plan[1]["args"]["match"] == "contains"
    assert plan[2]["tool"] == "press"
    assert plan[2]["args"]["key"] == "Enter"


def test_glue_planner_maps_assert_text_error():
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=_FakePlanner(),
        plan_executor=ex,
        snapshot_runner=None,
        storage=_FakeStorage(),
        log=None,
        reporter=None,
        llm=None,
        settings=_GlueSettings(),
    )

    class Spec4:
        id = "qa2"
        steps = [type("S", (), {"text": "assert that 'Invalid password' is shown"})()]

    run_id = orch.run_live(Spec4())
    assert run_id == "run-qa2"
    plan = ex.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[1]["tool"] == "assertText"
    args = plan[1]["args"]
    assert args["expected"] == "Invalid password"
    assert args["match"] == "contains"
    assert args["target"]["text"] == "Invalid password"

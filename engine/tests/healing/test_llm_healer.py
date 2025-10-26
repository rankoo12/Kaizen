import json

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


class FakeLLM:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.payload


def test_llm_healer_success_path():
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "llm"

    proposal = json.dumps({"primary": {"type": "css", "value": "#login"}})
    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        llm=FakeLLM(proposal),
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True


def test_llm_healer_malformed_falls_back_to_deterministic_if_available():
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "llm"

    # Deterministic fallback healer provided
    from engine.core.healing.selector_healer import DeterministicHealer

    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        healer=DeterministicHealer(),
        llm=FakeLLM("not json"),
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True  # healed by deterministic fallback


def test_llm_healer_proposes_not_visible_candidate_rejected():
    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "llm"

    bad = json.dumps({"primary": {"type": "css", "value": "#login", "visible": False}})
    ex = DeterministicPlanExecutor(
        handlers={"click": OkHandler()},
        resolver=Resolver(),
        settings=_S(),
        llm=FakeLLM(bad),
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))
    assert res[0].ok is False and res[0].reason == "not_visible"

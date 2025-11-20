from engine.core.commands.action_handler import IActionHandler, StepResult, ExecCtx
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor


class FailClick(IActionHandler):
    def execute(self, tool_call, ctx: ExecCtx) -> StepResult:
        if tool_call.get("tool") == "click" and tool_call.get("meta", {}).get("resolved"):
            if tool_call["meta"]["resolved"].get("value") == "#fallback":
                return StepResult(ok=True)
        return StepResult(ok=False, reason="missing")


def test_pagebrain_candidates_used_before_healer(monkeypatch):
    handlers = {"click": FailClick()}
    plan = [{
        "tool": "click",
        "args": {"target": {"text": "Login"}},
        "meta": {
            "pagebrain": {
                "candidates": [
                    {"selector": {"type": "css", "value": "#fallback"}}
                ],
                "label_source": "pagebrain_candidate"
            }
        }
    }]
    settings = type("_S", (), {"HEALER_ENABLED": True, "HEALER_PATH": "deterministic"})()
    ex = DeterministicPlanExecutor(handlers=handlers, resolver=None, settings=settings, healer=None)
    res = ex.execute(plan, ctx=ExecCtx(run_id="run-heal"))
    assert res and res[0].ok

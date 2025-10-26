from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def test_click_result_includes_signature_from_resolved_candidate():
    class Resolver:
        def find(self, target: dict):
            return [
                {
                    "type": "css",
                    "value": "#login",
                    "id": "login",
                    "classes": ["btn", "primary"],
                    "attrs": {"data-testid": "login-btn"},
                    "role": "button",
                    "name": "Login",
                    "visible": True,
                    "enabled": True,
                }
            ]

    ex = DeterministicPlanExecutor(handlers={"click": OkHandler()}, resolver=Resolver())
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert res[0].ok is True
    sig = res[0].signature or {}
    # Required identity pieces captured
    assert sig.get("type") == "css" and sig.get("value") == "#login"
    assert sig.get("id") == "login" and sig.get("testid") == "login-btn"
    assert sig.get("role") == "button" and sig.get("name") == "Login"
    assert sig.get("visible") is True and sig.get("enabled") is True

from __future__ import annotations

from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class CustomHandler(IActionHandler):
    """Execute a sandboxed custom script via page.evaluate.

    Note: security posture should restrict this in production; here we trust local runs.
    """

    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        script = (tool_call.get("args") or {}).get("script")
        try:
            result = self._browser.run_coro(self._browser.evaluate(str(script)))
        except Exception:
            return StepResult(ok=False, reason="custom_script_error")
        # If script explicitly returns False, treat as failure
        if result is False:
            return StepResult(ok=False, reason="custom_script_false")
        return StepResult(ok=True)

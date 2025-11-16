from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class CloseWindowHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        index = (tool_call.get("args") or {}).get("index")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.close_window(index=index))
            else:
                asyncio.run(self._browser.close_window(index=index))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="close_window_failed")

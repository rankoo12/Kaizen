from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class PressHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        key = tool_call.get("args", {}).get("key")
        runner = getattr(self._browser, "run_coro", None)
        if callable(runner):
            runner(self._browser.press(key))
        else:
            asyncio.run(self._browser.press(key))
        return StepResult(ok=True, reason=None)

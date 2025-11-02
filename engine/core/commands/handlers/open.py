from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class OpenHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        url = tool_call.get("args", {}).get("url")
        # Executor already guarded URL policy; just open
        runner = getattr(self._browser, "run_coro", None)
        if callable(runner):
            runner(self._browser.open(url))
        else:
            asyncio.run(self._browser.open(url))
        return StepResult(ok=True, reason=None)

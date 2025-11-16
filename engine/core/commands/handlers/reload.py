from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class ReloadHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.reload())
            else:
                asyncio.run(self._browser.reload())
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="reload_failed")

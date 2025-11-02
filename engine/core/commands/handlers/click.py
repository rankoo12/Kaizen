from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class ClickHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        runner = getattr(self._browser, "run_coro", None)
        if callable(runner):
            runner(self._browser.click(resolved))
        else:
            asyncio.run(self._browser.click(resolved))
        return StepResult(ok=True, reason=None)

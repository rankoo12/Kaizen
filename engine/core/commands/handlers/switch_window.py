from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class SwitchWindowHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        index = args.get("index")
        url_contains = args.get("urlContains")
        title_contains = args.get("titleContains")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.switch_window(index=index, url_contains=url_contains, title_contains=title_contains))
            else:
                asyncio.run(self._browser.switch_window(index=index, url_contains=url_contains, title_contains=title_contains))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="switch_window_failed")

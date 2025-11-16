from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class SelectHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        args = tool_call.get("args", {}) or {}
        option = args.get("option") or {}
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        if not isinstance(option, dict) or not option:
            return StepResult(ok=False, reason="missing_option")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.select_option(resolved, option))
            else:
                asyncio.run(self._browser.select_option(resolved, option))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="select_failed")

from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class DragHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        args = tool_call.get("args", {}) or {}
        dx = int(args.get("dx") or 0)
        dy = int(args.get("dy") or 0)
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.drag(resolved, dx, dy))
            else:
                asyncio.run(self._browser.drag(resolved, dx, dy))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="drag_failed")

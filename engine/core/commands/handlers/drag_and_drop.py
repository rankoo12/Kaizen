from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class DragAndDropHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        src = meta.get("resolved")
        dst = meta.get("resolved_to")
        if src is None or dst is None:
            return StepResult(ok=False, reason="missing_drag_targets")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.drag_and_drop(src, dst))
            else:
                asyncio.run(self._browser.drag_and_drop(src, dst))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="drag_and_drop_failed")

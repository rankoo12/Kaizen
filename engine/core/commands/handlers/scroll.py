from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class ScrollHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        # Support either (x,y) or (direction, amount)
        x = args.get("x")
        y = args.get("y")
        if x is None or y is None:
            direction = str(args.get("direction") or "down").lower()
            amount = int(args.get("amount") or 0)
            if direction == "up":
                x, y = 0, -abs(amount)
            elif direction == "down":
                x, y = 0, abs(amount)
            elif direction == "left":
                x, y = -abs(amount), 0
            elif direction == "right":
                x, y = abs(amount), 0
            else:
                x, y = 0, 0
        try:
            runner = getattr(self._browser, "run_coro", None)
            if callable(runner):
                runner(self._browser.scroll(int(x), int(y)))
            else:
                asyncio.run(self._browser.scroll(int(x), int(y)))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="scroll_failed")

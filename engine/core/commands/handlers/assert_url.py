from __future__ import annotations

import re
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class AssertUrlHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        expected = args.get("expected")
        match = args.get("match") or "equals"
        try:
            href = self._browser.run_coro(self._browser.evaluate("location.href"))
        except Exception:
            href = ""
        if match == "equals":
            ok = str(href) == str(expected)
        elif match == "contains":
            ok = str(expected) in str(href)
        elif match == "regex":
            try:
                ok = bool(re.search(str(expected), str(href)))
            except re.error:
                ok = False
        else:
            ok = False
        return StepResult(ok=ok, reason=None if ok else "assert_url_failed")

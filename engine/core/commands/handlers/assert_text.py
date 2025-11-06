from __future__ import annotations

import re
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


class AssertTextHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        expected = args.get("expected")
        match = args.get("match") or "equals"
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        if resolved is None:
            return StepResult(ok=False, reason="missing_target")
        selector = to_selector_string(resolved)
        import json as _json
        script = (
            "(function(s){var el=document.querySelector(s);"
            "if(!el) return '';"
            "return (el.innerText||el.textContent)||'';})(" + _json.dumps(selector) + ")"
        )
        try:
            text = self._browser.run_coro(self._browser.evaluate(script)) or ""
        except Exception:
            text = ""

        if match == "equals":
            ok = str(text) == str(expected)
        elif match == "contains":
            ok = str(expected) in str(text)
        elif match == "regex":
            try:
                ok = bool(re.search(str(expected), str(text)))
            except re.error:
                ok = False
        else:
            ok = False
        return StepResult(ok=ok, reason=None if ok else "assert_text_failed")

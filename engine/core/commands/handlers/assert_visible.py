from __future__ import annotations

import time
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.orchestrator import reasons as R
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


class AssertVisibleHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        if resolved is None:
            return StepResult(ok=False, reason=R.MISSING_TARGET)

        selector = to_selector_string(resolved)
        import json as _json
        script = (
            "(function(s){var el=document.querySelector(s);"
            "if(!el) return false;var cs=getComputedStyle(el);"
            "if(cs.visibility==='hidden'||cs.display==='none') return false;"
            "var r=el.getBoundingClientRect();return (r.width>0 && r.height>0);})(" + _json.dumps(selector) + ")"
        )
        try:
            ok = bool(self._browser.run_coro(self._browser.evaluate(script)))
            return StepResult(ok=ok, reason=None if ok else R.NOT_VISIBLE)
        except Exception:
            # brief retry once in case of transient DOM
            try:
                time.sleep(0.05)
                ok = bool(self._browser.run_coro(self._browser.evaluate(script)))
                return StepResult(ok=ok, reason=None if ok else R.NOT_VISIBLE)
            except Exception:
                return StepResult(ok=False, reason=R.NOT_VISIBLE)

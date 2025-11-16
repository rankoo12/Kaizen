from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.orchestrator import reasons as R
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


class RightClickHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.right_click(resolved))
            else:
                asyncio.run(self._browser.right_click(resolved))
            return StepResult(ok=True, reason=None)
        except Exception:
            try:
                import re

                fallbacks: list[str] = []
                sel = to_selector_string(resolved)
                if isinstance(sel, str):
                    base = sel.split(" ")[0].split(">")[0].split(":")[0]
                    base = re.sub(r"\[.*?\]", "", base).strip()
                    if base and base != sel:
                        fallbacks.append(base)
                for fb in fallbacks:
                    try:
                        if callable(runner):
                            runner(self._browser.right_click(fb))
                        else:
                            asyncio.run(self._browser.right_click(fb))
                        meta["resolved"] = {"type": "css", "value": fb, "visible": True, "enabled": True}
                        tool_call["meta"] = meta
                        return StepResult(ok=True, reason=None)
                    except Exception:
                        continue
            except Exception:
                pass
            return StepResult(ok=False, reason=R.CLICK_TIMEOUT)

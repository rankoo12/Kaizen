from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.orchestrator import reasons as R
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


class TypeHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        text = tool_call.get("args", {}).get("text", "")
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.type(resolved, text))
            else:
                asyncio.run(self._browser.type(resolved, text))
            return StepResult(ok=True, reason=None)
        except Exception:
            # Best-effort fallback similar to click: generalize CSS and try label association
            try:
                import re
                fallbacks: list[str] = []
                sel = to_selector_string(resolved)
                if isinstance(sel, str):
                    base = sel.split(" ")[0].split(">")[0].split(":")[0]
                    base = re.sub(r"\[.*?\]", "", base).strip()
                    if base and base != sel:
                        fallbacks.append(base)
                # Build from target label text when available
                target = (tool_call.get("args") or {}).get("target") or {}
                label_text = None
                if isinstance(target, dict):
                    t = target.get("text")
                    if isinstance(t, str) and t.strip():
                        label_text = t.strip()
                if label_text:
                    fallbacks.append(f'label:has-text("{label_text}") input')
                    try:
                        tokens = re.findall(r"[A-Za-z]+", label_text)
                        kw = max(tokens, key=len) if tokens else None
                    except Exception:
                        kw = None
                    if kw and kw.lower() != label_text.lower():
                        fallbacks.append(
                            f'input[name*="{kw}" i], input[aria-label*="{kw}" i], input[placeholder*="{kw}" i]'
                        )
                tried = set()
                for fb in fallbacks:
                    if not fb or fb in tried:
                        continue
                    tried.add(fb)
                    try:
                        if callable(runner):
                            runner(self._browser.type(fb, text))
                        else:
                            asyncio.run(self._browser.type(fb, text))
                        # Update resolved to reflect selector used
                        try:
                            meta = tool_call.get("meta") or {}
                            cand = {"type": "css", "value": fb, "visible": True, "enabled": True}
                            meta["resolved"] = cand
                            tool_call["meta"] = meta
                        except Exception:
                            pass
                        return StepResult(ok=True, reason=None)
                    except Exception:
                        continue
            except Exception:
                pass
            return StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)

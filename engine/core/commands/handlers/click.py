from __future__ import annotations

import asyncio
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.orchestrator import reasons as R
from engine.core.commands.selector import to_selector_string
from engine.core.browser.browser_port import IBrowser


class ClickHandler(IActionHandler):
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
                runner(self._browser.click(resolved))
            else:
                asyncio.run(self._browser.click(resolved))
            return StepResult(ok=True, reason=None)
        except Exception:
            # Best-effort fallback: generalize CSS selector or try label-based association
            try:
                import re

                fallbacks: list[str] = []
                sel = to_selector_string(resolved)
                # Generalize CSS like "input[type='text']" -> "input"
                if isinstance(sel, str):
                    base = sel.split(" ")[0].split(">")[0].split(":")[0]
                    base = re.sub(r"\[.*?\]", "", base).strip()
                    if base and base != sel:
                        fallbacks.append(base)
                # Label text association if original target had text
                target = (tool_call.get("args") or {}).get("target") or {}
                label_text = None
                if isinstance(target, dict):
                    t = target.get("text")
                    if isinstance(t, str) and t.strip():
                        label_text = t.strip()
                if label_text:
                    # Try exact label text
                    fallbacks.append(f'label:has-text("{label_text}") input')
                    # Heuristic keyword from label text (e.g., "the Name field" -> "Name")
                    try:
                        tokens = re.findall(r"[A-Za-z]+", label_text)
                        kw = max(tokens, key=len) if tokens else None
                    except Exception:
                        kw = None
                    if kw and kw.lower() != label_text.lower():
                        fallbacks.append(
                            f'input[name*="{kw}" i], input[aria-label*="{kw}" i], input[placeholder*="{kw}" i]'
                        )
                # Try fallbacks
                tried = set()
                for fb in fallbacks:
                    if not fb or fb in tried:
                        continue
                    tried.add(fb)
                    try:
                        if callable(runner):
                            runner(self._browser.click(fb))
                        else:
                            asyncio.run(self._browser.click(fb))
                        # Update resolved to reflect the actual selector used
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
            return StepResult(ok=False, reason=R.CLICK_TIMEOUT)

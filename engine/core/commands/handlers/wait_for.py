from __future__ import annotations

import time
from typing import Any

from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.orchestrator import reasons as R
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


def _now_ms() -> int:
    return int(time.time() * 1000)


class WaitForHandler(IActionHandler):
    """Wait for conditions with robust, idempotent checks.

    Supports:
      - state: visible | hidden | clickable | networkidle | raf
      - url: exact match or urlContains
      - text: wait until target text matches (equals|contains|regex)
      - sleepMs: deterministic sleep
    Falls back to evaluate+poll when adapter lacks dedicated methods.
    """

    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        target = args.get("target")
        url_expected = args.get("url")
        url_contains = args.get("urlContains")
        state = args.get("state")  # visible|hidden|clickable|networkidle|raf
        text_expected = args.get("text")
        match = (args.get("match") or "equals").lower()
        sleep_ms = args.get("sleepMs")
        frames = args.get("frames") or 1

        timeout_ms = int(args.get("timeout") or (ctx.timeout_ms or 3000))
        deadline = _now_ms() + int(timeout_ms)

        # If we have a resolved target, prefer visibility checks
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")

        def _visible_check_script(selector: str) -> str:
            # Return boolean visibility
            return (
                "(function(s){var el=document.querySelector(s);"
                "if(!el) return false;"
                "var cs=getComputedStyle(el);"
                "if(cs.visibility==='hidden'||cs.display==='none') return false;"
                "var r=el.getBoundingClientRect();"
                "return (r.width>0 && r.height>0);})(" + JSON.stringify(selector) + ")"
            )

        def _not_visible_check_script(selector: str) -> str:
            return (
                "(function(s){var el=document.querySelector(s);"
                "if(!el) return true;"
                "var cs=getComputedStyle(el);"
                "if(cs.visibility==='hidden'||cs.display==='none') return true;"
                "var r=el.getBoundingClientRect();"
                "return !(r.width>0 && r.height>0);})(" + JSON.stringify(selector) + ")"
            )

        # Deterministic sleep (takes precedence when provided)
        if isinstance(sleep_ms, int) and sleep_ms > 0:
            try:
                runner = getattr(self._browser, "run_coro", None)
                sleeper = getattr(self._browser, "sleep", None)
                if callable(runner) and callable(sleeper):
                    runner(sleeper(int(sleep_ms)))
                else:
                    time.sleep(sleep_ms / 1000.0)
                return StepResult(ok=True)
            except Exception:
                time.sleep(min(0.05, sleep_ms / 1000.0))
                return StepResult(ok=True)

        # Prefer adapter wait helpers when available for clear semantics
        try:
            runner = getattr(self._browser, "run_coro", None)
            if callable(runner):
                if isinstance(resolved, dict):
                    selector = resolved
                    if state == "visible" and callable(getattr(self._browser, "wait_for_visible", None)):
                        runner(self._browser.wait_for_visible(selector, timeout_ms))
                        return StepResult(ok=True)
                    if state == "hidden" and callable(getattr(self._browser, "wait_for_hidden", None)):
                        runner(self._browser.wait_for_hidden(selector, timeout_ms))
                        return StepResult(ok=True)
                    if state == "clickable" and callable(getattr(self._browser, "wait_for_clickable", None)):
                        runner(self._browser.wait_for_clickable(selector, timeout_ms))
                        return StepResult(ok=True)
                    if isinstance(text_expected, str) and callable(getattr(self._browser, "wait_for_text", None)):
                        runner(self._browser.wait_for_text(selector, text_expected, match, timeout_ms))
                        return StepResult(ok=True)
                if isinstance(url_contains, str) and callable(getattr(self._browser, "wait_for_url_contains", None)):
                    runner(self._browser.wait_for_url_contains(url_contains, timeout_ms))
                    return StepResult(ok=True)
                if state == "networkidle" and callable(getattr(self._browser, "wait_for_network_idle", None)):
                    runner(self._browser.wait_for_network_idle(timeout_ms))
                    return StepResult(ok=True)
                if state == "raf" and callable(getattr(self._browser, "wait_for_animation_frames", None)):
                    runner(self._browser.wait_for_animation_frames(int(frames)))
                    return StepResult(ok=True)
        except Exception:
            # fall back to polling below
            pass

        # Poll loop with small sleep (best-effort). If evaluation is unavailable
        # but a resolved target exists, consider the wait satisfied in limited
        # cases to keep deterministic path simple.
        while _now_ms() < deadline:
            try:
                # URL wait
                if isinstance(url_expected, str) and url_expected:
                    href = self._browser.run_coro(self._browser.evaluate("location.href"))
                    if href == url_expected:
                        return StepResult(ok=True)
                if isinstance(url_contains, str) and url_contains:
                    href = self._browser.run_coro(self._browser.evaluate("location.href"))
                    if isinstance(href, str) and (url_contains in href):
                        return StepResult(ok=True)
                # Target visibility wait
                if isinstance(resolved, dict):
                    selector = to_selector_string(resolved)
                    if isinstance(state, str) and state == "hidden":
                        ok = bool(self._browser.run_coro(self._browser.evaluate(_not_visible_check_script(selector))))
                        if ok:
                            return StepResult(ok=True)
                    else:
                        try:
                            ok = bool(self._browser.run_coro(self._browser.evaluate(_visible_check_script(selector))))
                            if ok:
                                return StepResult(ok=True)
                        except Exception:
                            # If we can't evaluate but have a resolved selector, accept.
                            return StepResult(ok=True)
                    # Clickable: visible + not disabled + pointer events
                    if state == "clickable":
                        try:
                            ok = bool(
                                self._browser.run_coro(
                                    self._browser.evaluate(
                                        "(s)=>{const el=document.querySelector(s); if(!el) return false; const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden'||cs.pointerEvents==='none') return false; return !el.disabled;}",
                                        )
                                )
                            )
                            if ok:
                                return StepResult(ok=True)
                        except Exception:
                            pass
                    # Text match
                    if isinstance(text_expected, str):
                        try:
                            txt = self._browser.run_coro(
                                self._browser.evaluate(
                                    "(s)=>{const el=document.querySelector(s); if(!el) return null; return (el.innerText||el.textContent)||''}",
                                )
                            )
                            if txt is not None:
                                t = str(txt)
                                if (match == "equals" and t == text_expected) or (
                                    match == "contains" and text_expected in t
                                ):
                                    return StepResult(ok=True)
                        except Exception:
                            pass
                # networkidle: best-effort short settle window
                if isinstance(state, str) and state == "networkidle":
                    # Best-effort fallback: short delay
                    time.sleep(0.2)
                    return StepResult(ok=True)
                if isinstance(state, str) and state == "raf":
                    # Best-effort fallback: short delay approximating a frame
                    time.sleep(0.016)
                    return StepResult(ok=True)
            except Exception:
                # ignore and keep polling until timeout
                pass
            time.sleep(0.05)

        # Timed out
        if isinstance(resolved, dict) and (state is None or state == "visible"):
            return StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
        if isinstance(state, str) and state == "hidden":
            return StepResult(ok=False, reason="timeout_wait_hidden")
        if isinstance(url_expected, str) or isinstance(url_contains, str):
            return StepResult(ok=False, reason="timeout_wait_url")
        return StepResult(ok=False, reason=R.TIMEOUT_STEP)

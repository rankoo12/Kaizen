from __future__ import annotations

import asyncio
from typing import List
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser


class UploadHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        args = tool_call.get("args", {}) or {}
        files: List[str] = args.get("files") or []
        if resolved is None:
            return StepResult(ok=False, reason="no_resolved_target")
        if not isinstance(files, list) or not files:
            return StepResult(ok=False, reason="missing_files")
        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                runner(self._browser.set_input_files(resolved, files))
            else:
                asyncio.run(self._browser.set_input_files(resolved, files))
            return StepResult(ok=True)
        except Exception:
            return StepResult(ok=False, reason="upload_failed")

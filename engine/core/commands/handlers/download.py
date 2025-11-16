from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Optional

from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from engine.core.browser.browser_port import IBrowser
from engine.core.config.settings import settings as _settings


class DownloadHandler(IActionHandler):
    def __init__(self, browser: IBrowser):
        self._browser = browser

    def _sha256(self, p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as fp:
            for chunk in iter(lambda: fp.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        args = tool_call.get("args", {}) or {}
        url: Optional[str] = args.get("url")
        target = args.get("target")
        filename: Optional[str] = args.get("filename")
        checksum: Optional[str] = args.get("checksum")
        algo: str = (args.get("algo") or "sha256").lower()

        # Destination directory: logs/downloads/<run_id>
        run_id = str(getattr(ctx, "run_id", "run"))
        logs_dir: Path = getattr(_settings, "LOGS_DIR", Path("logs"))
        out_dir = logs_dir / "downloads" / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # Resolved locator if present
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")

        runner = getattr(self._browser, "run_coro", None)
        try:
            if callable(runner):
                info = runner(
                    self._browser.download(
                        locator=resolved if isinstance(resolved, dict) else None,
                        url=url,
                        filename=filename,
                        out_dir=str(out_dir),
                    )
                )
            else:
                info = asyncio.run(
                    self._browser.download(
                        locator=resolved if isinstance(resolved, dict) else None,
                        url=url,
                        filename=filename,
                        out_dir=str(out_dir),
                    )
                )
        except Exception:
            return StepResult(ok=False, reason="download_failed")

        try:
            p = Path(info.get("path"))
            ok = p.exists() and p.is_file()
        except Exception:
            ok = False
        if not ok:
            return StepResult(ok=False, reason="download_missing")

        sig = {"filename": info.get("filename"), "path": str(p)}
        if algo == "sha256":
            digest = self._sha256(p)
            sig["sha256"] = digest
            if isinstance(checksum, str) and checksum:
                if digest.lower() != checksum.lower():
                    return StepResult(ok=False, reason="checksum_mismatch", signature=sig)
        # Future: support other algorithms on demand
        return StepResult(ok=True, reason=None, signature=sig)

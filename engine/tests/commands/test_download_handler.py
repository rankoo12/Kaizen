from pathlib import Path
from engine.core.commands.handlers.download import DownloadHandler
from engine.core.commands.action_handler import ExecCtx
from engine.core.config import settings as _smod
from engine.core.config.settings import settings


class FB:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = []

    def run_coro(self, coro):
        import asyncio
        return asyncio.run(coro)

    async def download(self, *, locator=None, url=None, filename=None, out_dir: str):
        # Simulate writing the file to out_dir
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        name = filename or "file.bin"
        p = Path(out_dir) / name
        p.write_bytes(self.content)
        self.calls.append((locator, url, filename, out_dir))
        return {"path": str(p), "filename": name}


def test_download_handler_writes_and_checksums(tmp_path, monkeypatch):
    # redirect logs dir to tmp
    monkeypatch.setattr(settings, "LOGS_DIR", tmp_path)
    content = b"abc123"
    b = FB(content)
    h = DownloadHandler(b)
    # compute expected sha256
    import hashlib

    exp = hashlib.sha256(content).hexdigest()
    ctx = ExecCtx(run_id="r-dl")
    ok = h.execute({"tool": "download", "args": {"url": "data:text/plain,abc123", "filename": "a.txt", "checksum": exp}}, ctx)
    assert ok.ok, ok.reason
    # mismatch
    bad = h.execute({"tool": "download", "args": {"url": "data:text/plain,abc123", "filename": "b.txt", "checksum": "deadbeef"}}, ctx)
    assert not bad.ok and bad.reason == "checksum_mismatch"

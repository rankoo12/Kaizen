import urllib.parse
import hashlib
import pytest

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.commands.action_handler import ExecCtx
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.download import DownloadHandler
from engine.core.artifacts.store import FSArtifactStore
from engine.core.config.settings import settings


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html, safe="")


@pytest.mark.e2e
def test_download_text_file_and_artifacts_list(tmp_path, monkeypatch):
    # redirect logs dir to tmp so we don't write into repo
    monkeypatch.setattr(settings, "LOGS_DIR", tmp_path)
    html = "<html><body><a id='dl' href='data:text/plain,Hello%20World' download='hello.txt'>DL</a></body></html>"
    url = _data_url(html)
    browser = PlaywrightBrowser()
    handlers = {"open": OpenHandler(browser), "download": DownloadHandler(browser)}
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))

    # Prepare expected checksum
    text = "Hello World"
    exp_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    plan = [
        {"tool": "open", "args": {"url": url}},
        {"tool": "download", "args": {"target": {"css": "#dl"}, "filename": "hello.txt", "checksum": exp_sha}},
    ]
    run_id = "dl-e2e"
    res = execu.execute(plan, ctx=ExecCtx(run_id=run_id, timeout_ms=3000))
    assert all(r.ok for r in res), [(r.ok, r.reason) for r in res]

    # Verify file exists in logs/downloads/<run_id>/hello.txt
    dest = settings.LOGS_DIR / "downloads" / run_id / "hello.txt"
    assert dest.exists() and dest.read_text(encoding="utf-8") == text

    # Artifacts store lists the download
    store = FSArtifactStore(settings.LOGS_DIR, settings.SNAPSHOTS_DIR)
    names = {item["name"] for item in store.list(run_id)}
    assert f"download/{dest.name}" in names

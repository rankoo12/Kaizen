import urllib.parse
import pathlib

import pytest

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.select import SelectHandler
from engine.core.commands.handlers.upload import UploadHandler
from engine.core.commands.handlers.drag_and_drop import DragAndDropHandler
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.commands.action_handler import ExecCtx


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html, safe="")


@pytest.mark.e2e
def test_select_dropdown_changes_value():
    html = """
    <html><body>
    <select id="pet">
      <option value="dog">Dog</option>
      <option value="cat">Cat</option>
    </select>
    </body></html>
    """
    browser = PlaywrightBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "select": SelectHandler(browser),
    }
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    plan = [
        {"tool": "open", "args": {"url": _data_url(html)}},
        {"tool": "select", "args": {"target": {"css": "#pet"}, "option": {"value": "cat"}}},
    ]
    ctx = ExecCtx(run_id="e2e-select", timeout_ms=3000)
    res = execu.execute(plan, ctx=ctx)
    assert all(r.ok for r in res)
    val = browser.run_coro(browser.evaluate("document.querySelector('#pet').value"))
    assert val == "cat"


@pytest.mark.e2e
def test_upload_sets_file_name(tmp_path: pathlib.Path):
    f = tmp_path / "sample.txt"
    f.write_text("hello")
    html = """
    <html><body>
    <input id="f" type="file" />
    </body></html>
    """
    browser = PlaywrightBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "upload": UploadHandler(browser),
    }
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    plan = [
        {"tool": "open", "args": {"url": _data_url(html)}},
        {"tool": "upload", "args": {"target": {"css": "#f"}, "files": [str(f)]}},
    ]
    ctx = ExecCtx(run_id="e2e-upload", timeout_ms=3000)
    res = execu.execute(plan, ctx=ctx)
    assert all(r.ok for r in res)
    name = browser.run_coro(
        browser.evaluate("(function(){var f=document.getElementById('f'); return f.files && f.files[0] && f.files[0].name || ''})()")
    )
    assert name == f.name


@pytest.mark.e2e
def test_drag_and_drop_fires_drop_handler():
    html = """
    <html>
    <head>
    <script>
    function allow(ev){ ev.preventDefault(); }
    function dropped(ev){ ev.preventDefault(); var data=ev.dataTransfer.getData('text/plain'); ev.target.textContent='Dropped '+data; }
    </script>
    </head>
    <body>
      <div id="src" draggable="true" ondragstart="event.dataTransfer.setData('text/plain','SRC')">SRC</div>
      <div id="dst" ondragover="allow(event)" ondrop="dropped(event)">DST</div>
    </body></html>
    """
    browser = PlaywrightBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "dragAndDrop": DragAndDropHandler(browser),
    }
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    plan = [
        {"tool": "open", "args": {"url": _data_url(html)}},
        {"tool": "dragAndDrop", "args": {"target": {"css": "#src"}, "to": {"css": "#dst"}}},
    ]
    ctx = ExecCtx(run_id="e2e-dnd", timeout_ms=4000)
    res = execu.execute(plan, ctx=ctx)
    assert all(r.ok for r in res)
    text = browser.run_coro(browser.evaluate("document.getElementById('dst').textContent"))
    assert text.startswith("Dropped SRC")

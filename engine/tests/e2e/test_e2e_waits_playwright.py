import urllib.parse
import pytest

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.commands.action_handler import ExecCtx
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.wait_for import WaitForHandler


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html, safe="")


@pytest.mark.e2e
def test_wait_visible_hidden_text_and_url_contains():
    html = """
    <html>
    <body>
      <div id="msg" style="display:none">Hello</div>
      <script>
        setTimeout(()=>{ document.getElementById('msg').style.display='block'; }, 50);
        setTimeout(()=>{ document.getElementById('msg').textContent='Hello World'; }, 100);
      </script>
    </body>
    </html>
    """
    url = _data_url(html)
    browser = PlaywrightBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "waitFor": WaitForHandler(browser),
    }
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    # open -> wait visible -> wait text contains
    plan = [
        {"tool": "open", "args": {"url": url}},
        {"tool": "waitFor", "args": {"target": {"css": "#msg"}, "state": "visible", "timeout": 2000}},
        {"tool": "waitFor", "args": {"target": {"css": "#msg"}, "text": "World", "match": "contains", "timeout": 2000}},
    ]
    res = execu.execute(plan, ctx=ExecCtx(run_id="waits1", timeout_ms=2000))
    assert all(r.ok for r in res)
    # urlContains works
    res2 = execu.execute([{"tool": "waitFor", "args": {"urlContains": "data:text/html"}}], ctx=ExecCtx(run_id="waits2", timeout_ms=500))
    assert res2[0].ok


@pytest.mark.e2e
def test_wait_sleep_and_raf():
    html = "<html><body><div id='a'>A</div></body></html>"
    url = _data_url(html)
    browser = PlaywrightBrowser()
    handlers = {"open": OpenHandler(browser), "waitFor": WaitForHandler(browser)}
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    res = execu.execute([{"tool": "open", "args": {"url": url}}], ctx=ExecCtx(run_id="waits3", timeout_ms=1000))
    assert all(r.ok for r in res)
    # sleep then raf
    assert execu.execute([{"tool": "waitFor", "args": {"sleepMs": 10}}], ctx=ExecCtx(run_id="sleep", timeout_ms=1000))[0].ok
    assert execu.execute([{"tool": "waitFor", "args": {"state": "raf", "frames": 2}}], ctx=ExecCtx(run_id="raf", timeout_ms=1000))[0].ok

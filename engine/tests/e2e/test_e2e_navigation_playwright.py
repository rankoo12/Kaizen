import urllib.parse
import pytest

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.commands.action_handler import ExecCtx
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.new_tab import NewTabHandler
from engine.core.commands.handlers.switch_tab import SwitchTabHandler
from engine.core.commands.handlers.close_tab import CloseTabHandler
from engine.core.commands.handlers.reload import ReloadHandler
from engine.core.commands.handlers.back import BackHandler
from engine.core.commands.handlers.forward import ForwardHandler


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html, safe="")


@pytest.mark.e2e
def test_new_tab_switch_close_and_url():
    html1 = "<html><body><h1>One</h1></body></html>"
    html2 = "<html><body><h1>Two</h1></body></html>"
    url1 = _data_url(html1)
    url2 = _data_url(html2)

    browser = PlaywrightBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "newTab": NewTabHandler(browser),
        "switchTab": SwitchTabHandler(browser),
        "closeTab": CloseTabHandler(browser),
    }
    execu = DeterministicPlanExecutor(browser=browser, handlers=handlers, resolver=ElementResolver(browser=browser))
    plan = [
        {"tool": "open", "args": {"url": url1}},
        {"tool": "newTab", "args": {"url": url2}},
        {"tool": "switchTab", "args": {"index": 0}},
    ]
    res = execu.execute(plan, ctx=ExecCtx(run_id="nav-tabs", timeout_ms=3000))
    assert res[0].ok, res[0].reason
    assert res[1].ok, res[1].reason
    assert res[2].ok, res[2].reason
    href = browser.run_coro(browser.evaluate("location.href"))
    assert href == url1
    # switch to tab 1 and close it
    res2 = execu.execute([{"tool": "switchTab", "args": {"index": 1}}, {"tool": "closeTab", "args": {}}], ctx=ExecCtx(run_id="nav-close", timeout_ms=3000))
    assert all(r.ok for r in res2)


## Note: back/forward e2e on data: URLs is browser-implementation dependent;
## we validate back/forward via contract tests only to avoid flake.

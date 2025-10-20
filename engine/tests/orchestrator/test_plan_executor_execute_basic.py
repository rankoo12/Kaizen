from typing import Any

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.action_handler import ExecCtx, IActionHandler, StepResult
from engine.core.orchestrator import reasons as R


class FakeBrowser:
    def __init__(self):
        self.opened = []
        self.clicked = []
        self.typed = []
        self.pressed = []


class OpenHandler(IActionHandler):
    def __init__(self, browser: FakeBrowser):
        self.browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        url = tool_call["args"]["url"]
        self.browser.opened.append(url)
        return StepResult(ok=True, reason=None)


class ClickHandler(IActionHandler):
    def __init__(self, browser: FakeBrowser):
        self.browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        if not resolved:
            return StepResult(ok=False, reason="no_resolved_target")
        self.browser.clicked.append(resolved)
        return StepResult(ok=True, reason=None)


class TypeHandler(IActionHandler):
    def __init__(self, browser: FakeBrowser):
        self.browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        meta = tool_call.get("meta") or {}
        resolved = meta.get("resolved")
        text = tool_call["args"].get("text")
        if not resolved:
            return StepResult(ok=False, reason="no_resolved_target")
        self.browser.typed.append((resolved, text))
        return StepResult(ok=True, reason=None)


class PressHandler(IActionHandler):
    def __init__(self, browser: FakeBrowser):
        self.browser = browser

    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        key = tool_call["args"].get("key")
        self.browser.pressed.append(key)
        return StepResult(ok=True, reason=None)


class FakeResolver:
    def __init__(self, mapping: dict[str, list[Any]]):
        self.mapping = mapping

    def find(self, target: dict) -> list[Any]:
        key = target.get("text") or ""
        return list(self.mapping.get(key, []))


def _make_executor(browser: FakeBrowser, resolver: FakeResolver, handlers: dict[str, IActionHandler]):
    return DeterministicPlanExecutor(
        browser=browser,
        handlers=handlers,
        resolver=resolver,
        log=None,
    )


def test_open_data_url_ok():
    browser = FakeBrowser()
    handlers = {"open": OpenHandler(browser)}
    resolver = FakeResolver({})
    ex = _make_executor(browser, resolver, handlers)

    plan = [{"tool": "open", "args": {"url": "data:text/html,hi"}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert len(res) == 1 and res[0].ok is True
    assert browser.opened == ["data:text/html,hi"]


def test_open_http_url_rejected():
    browser = FakeBrowser()
    handlers = {"open": OpenHandler(browser)}
    resolver = FakeResolver({})
    ex = _make_executor(browser, resolver, handlers)

    plan = [{"tool": "open", "args": {"url": "http://example.com"}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert len(res) == 1 and res[0].ok is False
    assert res[0].reason == R.URL_SCHEME_NOT_ALLOWED


def test_open_about_blank_ok():
    browser = FakeBrowser()
    handlers = {"open": OpenHandler(browser)}
    resolver = FakeResolver({})
    ex = _make_executor(browser, resolver, handlers)

    plan = [{"tool": "open", "args": {"url": "about:blank"}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert len(res) == 1 and res[0].ok is True
    assert browser.opened == ["about:blank"]


def test_click_resolves_single_candidate_ok():
    browser = FakeBrowser()
    handlers = {"click": ClickHandler(browser)}
    resolver = FakeResolver({"Login": [{"type": "css", "value": "#login", "visible": True, "enabled": True}]})
    ex = _make_executor(browser, resolver, handlers)

    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert res[0].ok is True
    assert isinstance(browser.clicked, list) and len(browser.clicked) == 1
    click0 = browser.clicked[0]
    assert click0.get("type") == "css" and click0.get("value") == "#login"


def test_click_zero_or_multi_candidates_fail():
    browser = FakeBrowser()
    handlers = {"click": ClickHandler(browser)}
    # no candidate for "Missing" and 2 candidates for "Ambiguous"
    resolver = FakeResolver({"Ambiguous": [1, 2]})
    ex = _make_executor(browser, resolver, handlers)

    res0 = ex.execute(
        [{"tool": "click", "args": {"target": {"text": "Missing"}}}], ctx=ExecCtx(run_id="r")
    )
    res2 = ex.execute(
        [{"tool": "click", "args": {"target": {"text": "Ambiguous"}}}], ctx=ExecCtx(run_id="r")
    )

    assert res0[0].ok is False and res0[0].reason == R.RESOLVE_ZERO
    assert res2[0].ok is False and res2[0].reason == R.RESOLVE_MULTI


def test_type_and_press_happy_paths():
    browser = FakeBrowser()
    handlers = {"type": TypeHandler(browser), "press": PressHandler(browser)}
    resolver = FakeResolver({"Query": [{"type": "css", "value": "input[name='q']"}]})
    ex = _make_executor(browser, resolver, handlers)

    plan = [
        {"tool": "type", "args": {"target": {"text": "Query"}, "text": "hello"}},
        {"tool": "press", "args": {"key": "Enter"}},
    ]
    res = ex.execute(plan, ctx=ExecCtx(run_id="r"))

    assert res[0].ok is True and res[1].ok is True
    assert browser.typed == [({"type": "css", "value": "input[name='q']"}, "hello")]
    assert browser.pressed == ["Enter"]

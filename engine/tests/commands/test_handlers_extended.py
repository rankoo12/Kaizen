from engine.core.commands.handlers.wait_for import WaitForHandler
from engine.core.commands.handlers.assert_visible import AssertVisibleHandler
from engine.core.commands.handlers.assert_text import AssertTextHandler
from engine.core.commands.handlers.assert_url import AssertUrlHandler
from engine.core.commands.handlers.custom import CustomHandler
from engine.core.commands.action_handler import ExecCtx


class FakeBrowser:
    def __init__(self):
        self.eval_calls = []
        self.eval_return = None

    async def evaluate(self, script: str):
        self.eval_calls.append(script)
        return self.eval_return

    # required by handlers using run_coro, expose sync wrapper
    def run_coro(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def test_wait_for_visible_target_ok(monkeypatch):
    b = FakeBrowser()
    b.eval_return = True
    h = WaitForHandler(browser=b)
    ctx = ExecCtx(run_id="r1", timeout_ms=1000)
    meta = {"resolved": {"type": "css", "value": "#login"}}
    res = h.execute({"tool": "waitFor", "args": {"target": {"text": "Login"}}, "meta": meta}, ctx)
    assert res.ok is True


def test_assert_visible_false_sets_reason():
    b = FakeBrowser()
    b.eval_return = False
    h = AssertVisibleHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    meta = {"resolved": {"type": "css", "value": "#hidden"}}
    res = h.execute({"tool": "assertVisible", "args": {"target": {"text": "hidden"}}, "meta": meta}, ctx)
    assert res.ok is False
    assert res.reason is not None


def test_assert_text_equals_ok():
    b = FakeBrowser()
    b.eval_return = "Hello World"
    h = AssertTextHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    meta = {"resolved": {"type": "css", "value": "#greeting"}}
    res = h.execute(
        {"tool": "assertText", "args": {"target": {"text": "greeting"}, "expected": "Hello World", "match": "equals"}, "meta": meta},
        ctx,
    )
    assert res.ok is True


def test_assert_url_contains_ok():
    b = FakeBrowser()
    b.eval_return = "https://example.com/login"
    h = AssertUrlHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    res = h.execute({"tool": "assertUrl", "args": {"expected": "example.com", "match": "contains"}}, ctx)
    assert res.ok is True


def test_custom_script_false_fails():
    b = FakeBrowser()
    b.eval_return = False
    h = CustomHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    res = h.execute({"tool": "custom", "args": {"script": "return false;"}}, ctx)
    assert res.ok is False

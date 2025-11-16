from engine.core.commands.handlers.wait_for import WaitForHandler
from engine.core.commands.action_handler import ExecCtx


class FB:
    def __init__(self):
        self.calls = []

    def run_coro(self, coro):
        import asyncio
        return asyncio.run(coro)

    async def wait_for_visible(self, loc, t):
        self.calls.append(("visible", loc, t))

    async def wait_for_hidden(self, loc, t):
        self.calls.append(("hidden", loc, t))

    async def wait_for_clickable(self, loc, t):
        self.calls.append(("clickable", loc, t))

    async def wait_for_text(self, loc, expected, match, t):
        self.calls.append(("text", loc, expected, match, t))

    async def wait_for_url_contains(self, sub, t):
        self.calls.append(("urlContains", sub, t))

    async def wait_for_network_idle(self, t):
        self.calls.append(("networkidle", t))

    async def wait_for_animation_frames(self, n):
        self.calls.append(("raf", n))

    async def sleep(self, ms):
        self.calls.append(("sleep", ms))

    async def evaluate(self, script: str):
        return "about:blank"


def _ctx():
    return ExecCtx(run_id="rw", timeout_ms=1234)


def test_wait_visible_hidden_clickable_routes_to_browser():
    b = FB()
    h = WaitForHandler(b)
    meta = {"resolved": {"css": "#a"}}
    assert h.execute({"tool": "waitFor", "args": {"state": "visible"}, "meta": meta}, _ctx()).ok
    assert h.execute({"tool": "waitFor", "args": {"state": "hidden"}, "meta": meta}, _ctx()).ok
    assert h.execute({"tool": "waitFor", "args": {"state": "clickable"}, "meta": meta}, _ctx()).ok
    kinds = [k for (k, *_) in b.calls]
    assert kinds == ["visible", "hidden", "clickable"]


def test_wait_text_and_url_contains_and_sleep_and_raf():
    b = FB()
    h = WaitForHandler(b)
    meta = {"resolved": {"css": "#t"}}
    assert h.execute({"tool": "waitFor", "args": {"target": {"css": "#t"}, "text": "Done", "match": "contains"}, "meta": meta}, _ctx()).ok
    assert h.execute({"tool": "waitFor", "args": {"urlContains": "blank"}}, _ctx()).ok
    assert h.execute({"tool": "waitFor", "args": {"sleepMs": 5}}, _ctx()).ok
    assert h.execute({"tool": "waitFor", "args": {"state": "raf", "frames": 2}}, _ctx()).ok
    kinds = [k for (k, *_) in b.calls]
    assert kinds == ["text", "urlContains", "sleep", "raf"]


def test_wait_networkidle_routes():
    b = FB()
    h = WaitForHandler(b)
    assert h.execute({"tool": "waitFor", "args": {"state": "networkidle"}}, _ctx()).ok
    assert b.calls == [("networkidle", 1234)]

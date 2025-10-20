import asyncio

from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler
from engine.core.commands.handlers.type import TypeHandler
from engine.core.commands.handlers.press import PressHandler
from engine.core.commands.action_handler import ExecCtx


class FakeBrowser:
    def __init__(self):
        self.opened = []
        self.clicked = []
        self.typed = []
        self.pressed = []

    async def open(self, url: str):
        self.opened.append(url)

    async def click(self, locator):
        self.clicked.append(locator)

    async def type(self, locator, text: str, clear: bool = False):
        self.typed.append((locator, text, clear))

    async def press(self, key: str):
        self.pressed.append(key)


def test_open_handler_calls_browser_open():
    b = FakeBrowser()
    h = OpenHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    h.execute({"tool": "open", "args": {"url": "about:blank"}}, ctx)
    assert b.opened == ["about:blank"]


def test_click_handler_uses_resolved_locator():
    b = FakeBrowser()
    h = ClickHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    meta = {"resolved": {"type": "css", "value": "#login"}}
    h.execute({"tool": "click", "args": {}, "meta": meta}, ctx)
    assert b.clicked == [{"type": "css", "value": "#login"}]


def test_type_handler_types_text_into_resolved():
    b = FakeBrowser()
    h = TypeHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    meta = {"resolved": {"type": "css", "value": "input[name='q']"}}
    h.execute({"tool": "type", "args": {"text": "hello"}, "meta": meta}, ctx)
    assert b.typed == [({"type": "css", "value": "input[name='q']"}, "hello", False)]


def test_press_handler_presses_key():
    b = FakeBrowser()
    h = PressHandler(browser=b)
    ctx = ExecCtx(run_id="r1")
    h.execute({"tool": "press", "args": {"key": "Enter"}}, ctx)
    assert b.pressed == ["Enter"]

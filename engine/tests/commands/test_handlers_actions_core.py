import asyncio

from engine.core.commands.action_handler import ExecCtx
from engine.core.commands.handlers.double_click import DoubleClickHandler
from engine.core.commands.handlers.right_click import RightClickHandler
from engine.core.commands.handlers.hover import HoverHandler
from engine.core.commands.handlers.focus import FocusHandler
from engine.core.commands.handlers.blur import BlurHandler
from engine.core.commands.handlers.clear import ClearHandler
from engine.core.commands.handlers.select import SelectHandler
from engine.core.commands.handlers.upload import UploadHandler
from engine.core.commands.handlers.drag import DragHandler
from engine.core.commands.handlers.drag_and_drop import DragAndDropHandler
from engine.core.commands.handlers.scroll import ScrollHandler


class FB:
    def __init__(self):
        self.calls = []

    async def dblclick(self, locator):
        self.calls.append(("dblclick", locator))

    async def right_click(self, locator):
        self.calls.append(("rightclick", locator))

    async def hover(self, locator):
        self.calls.append(("hover", locator))

    async def focus(self, locator):
        self.calls.append(("focus", locator))

    async def blur(self, locator):
        self.calls.append(("blur", locator))

    async def clear(self, locator):
        self.calls.append(("clear", locator))

    async def select_option(self, locator, option):
        self.calls.append(("select", locator, option))

    async def set_input_files(self, locator, files):
        self.calls.append(("upload", locator, list(files)))

    async def drag(self, locator, dx, dy):
        self.calls.append(("drag", locator, dx, dy))

    async def drag_and_drop(self, src, dst):
        self.calls.append(("dnd", src, dst))

    async def scroll(self, x, y):
        self.calls.append(("scroll", x, y))


def _ctx():
    return ExecCtx(run_id="r1")


def test_double_click():
    b = FB()
    h = DoubleClickHandler(b)
    meta = {"resolved": {"type": "css", "value": "#a"}}
    h.execute({"tool": "doubleClick", "args": {}, "meta": meta}, _ctx())
    assert b.calls == [("dblclick", {"type": "css", "value": "#a"})]


def test_right_click():
    b = FB()
    h = RightClickHandler(b)
    meta = {"resolved": {"type": "css", "value": ".menu"}}
    h.execute({"tool": "rightClick", "args": {}, "meta": meta}, _ctx())
    assert b.calls == [("rightclick", {"type": "css", "value": ".menu"})]


def test_hover_focus_blur_clear():
    b = FB()
    HoverHandler(b).execute({"tool": "hover", "meta": {"resolved": {"css": "#x"}}, "args": {}}, _ctx())
    FocusHandler(b).execute({"tool": "focus", "meta": {"resolved": {"css": "#x"}}, "args": {}}, _ctx())
    BlurHandler(b).execute({"tool": "blur", "meta": {"resolved": {"css": "#x"}}, "args": {}}, _ctx())
    ClearHandler(b).execute({"tool": "clear", "meta": {"resolved": {"css": "#x"}}, "args": {}}, _ctx())
    kinds = [k for (k, *_) in b.calls]
    assert kinds == ["hover", "focus", "blur", "clear"]


def test_select_upload_drag_dnd_scroll():
    b = FB()
    SelectHandler(b).execute(
        {"tool": "select", "meta": {"resolved": {"css": "select#pet"}}, "args": {"option": {"value": "cat"}}},
        _ctx(),
    )
    UploadHandler(b).execute(
        {"tool": "upload", "meta": {"resolved": {"css": "input[type=file]"}}, "args": {"files": ["/tmp/a.txt"]}},
        _ctx(),
    )
    DragHandler(b).execute(
        {"tool": "drag", "meta": {"resolved": {"css": "#drag"}}, "args": {"dx": 5, "dy": -3}}, _ctx()
    )
    DragAndDropHandler(b).execute(
        {
            "tool": "dragAndDrop",
            "meta": {"resolved": {"css": "#src"}, "resolved_to": {"css": "#dst"}},
            "args": {},
        },
        _ctx(),
    )
    ScrollHandler(b).execute({"tool": "scroll", "args": {"direction": "down", "amount": 120}}, _ctx())
    assert b.calls == [
        ("select", {"css": "select#pet"}, {"value": "cat"}),
        ("upload", {"css": "input[type=file]"}, ["/tmp/a.txt"]),
        ("drag", {"css": "#drag"}, 5, -3),
        ("dnd", {"css": "#src"}, {"css": "#dst"}),
        ("scroll", 0, 120),
    ]

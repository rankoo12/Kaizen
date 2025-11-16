from engine.core.commands.action_handler import ExecCtx
from engine.core.commands.handlers.reload import ReloadHandler
from engine.core.commands.handlers.back import BackHandler
from engine.core.commands.handlers.forward import ForwardHandler
from engine.core.commands.handlers.new_tab import NewTabHandler
from engine.core.commands.handlers.new_window import NewWindowHandler
from engine.core.commands.handlers.switch_tab import SwitchTabHandler
from engine.core.commands.handlers.switch_window import SwitchWindowHandler
from engine.core.commands.handlers.close_tab import CloseTabHandler
from engine.core.commands.handlers.close_window import CloseWindowHandler


class FB:
    def __init__(self):
        self.calls = []

    async def reload(self):
        self.calls.append(("reload",))

    async def go_back(self):
        self.calls.append(("back",))

    async def go_forward(self):
        self.calls.append(("forward",))

    async def new_tab(self, url=None):
        self.calls.append(("newTab", url))

    async def new_window(self, url=None):
        self.calls.append(("newWindow", url))

    async def switch_tab(self, index=None, url_contains=None, title_contains=None):
        self.calls.append(("switchTab", index, url_contains, title_contains))

    async def switch_window(self, index=None, url_contains=None, title_contains=None):
        self.calls.append(("switchWindow", index, url_contains, title_contains))

    async def close_tab(self, index=None):
        self.calls.append(("closeTab", index))

    async def close_window(self, index=None):
        self.calls.append(("closeWindow", index))


def _ctx():
    return ExecCtx(run_id="rnav")


def test_simple_nav_controls():
    b = FB()
    ReloadHandler(b).execute({"tool": "reload", "args": {}}, _ctx())
    BackHandler(b).execute({"tool": "back", "args": {}}, _ctx())
    ForwardHandler(b).execute({"tool": "forward", "args": {}}, _ctx())
    assert b.calls == [("reload",), ("back",), ("forward",)]


def test_tab_window_ops():
    b = FB()
    NewTabHandler(b).execute({"tool": "newTab", "args": {"url": "data:text/html,one"}}, _ctx())
    NewWindowHandler(b).execute({"tool": "newWindow", "args": {"url": "data:text/html,two"}}, _ctx())
    SwitchTabHandler(b).execute({"tool": "switchTab", "args": {"index": 0}}, _ctx())
    SwitchWindowHandler(b).execute({"tool": "switchWindow", "args": {"urlContains": "two"}}, _ctx())
    CloseTabHandler(b).execute({"tool": "closeTab", "args": {"index": 0}}, _ctx())
    CloseWindowHandler(b).execute({"tool": "closeWindow", "args": {}}, _ctx())
    assert b.calls == [
        ("newTab", "data:text/html,one"),
        ("newWindow", "data:text/html,two"),
        ("switchTab", 0, None, None),
        ("switchWindow", None, "two", None),
        ("closeTab", 0),
        ("closeWindow", None),
    ]

from __future__ import annotations

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler


class _FakeBrowser:
    async def open(self, url: str):
        return None

    async def click(self, locator):
        return None

    async def type(self, locator, text: str, clear: bool = False):
        return None

    async def press(self, key: str):
        return None

    async def screenshot(self, path: str):
        return None

    async def frames(self):
        return []

    async def evaluate(self, script: str):
        return None

    async def scroll(self, x: int, y: int):
        return None


class _FailResolver(IElementResolver):
    def resolve(self, query, snapshot):
        return {"primary": None, "fallbacks": [], "confidence": 0.0, "reason": "none"}

    def find(self, target: dict):
        # cause zero candidates to trigger healer path
        return []


class _CaptureHealer:
    def __init__(self):
        self.last_context = None

    def heal(self, failure: dict, context: dict):
        self.last_context = context
        return None


class _S:
    HEALER_ENABLED = True
    HEALER_PATH = "deterministic"
    ALLOWED_URL_SCHEMES = ["https://", "about:blank", "data:"]


def test_healer_receives_domain_from_last_open():
    browser = _FakeBrowser()
    healer = _CaptureHealer()
    execu = DeterministicPlanExecutor(
        browser=browser,
        handlers={"open": OpenHandler(browser), "click": ClickHandler(browser)},
        resolver=_FailResolver(),
        settings=_S(),
        healer=healer,
        storage=None,
    )
    plan = [
        {"tool": "open", "args": {"url": "https://example.com"}},
        {"tool": "click", "args": {"target": {"text": "Login"}}},
    ]
    class _Ctx:
        run_id = "r-x"
        timeout_ms = None
    execu.execute(plan, ctx=_Ctx())
    assert healer.last_context is not None
    assert healer.last_context.get("domain") == "example.com"

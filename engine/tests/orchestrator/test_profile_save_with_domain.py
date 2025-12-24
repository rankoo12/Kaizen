from __future__ import annotations

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler
from engine.core.storage.memory import InMemoryStorage


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


class _OneResolver(IElementResolver):
    def resolve(self, query, snapshot):
        return {"primary": {"type": "css", "value": "#login", "visible": True, "enabled": True}, "fallbacks": [], "confidence": 1.0, "reason": "stub"}

    def find(self, target: dict):
        return [{"type": "css", "value": "#login", "visible": True, "enabled": True}]


class _S:
    HEALER_ENABLED = False
    ALLOWED_URL_SCHEMES = ["https://", "about:blank", "data:"]


def test_profile_saved_with_domain_from_open():
    browser = _FakeBrowser()
    storage = InMemoryStorage()
    execu = DeterministicPlanExecutor(
        browser=browser,
        handlers={"open": OpenHandler(browser), "click": ClickHandler(browser)},
        resolver=_OneResolver(),
        settings=_S(),
        healer=None,
        storage=storage,
    )
    plan = [
        {"tool": "open", "args": {"url": "https://example.com"}},
        {"tool": "click", "args": {"target": {"css": "#login"}}},
    ]
    class _Ctx:
        run_id = "r-x"
        timeout_ms = None
    execu.execute(plan, ctx=_Ctx())
    # Ensure a profile was saved with domain example.com
    prof = storage.find_locator_profile(domain="example.com", tool="click", target_signature={})
    assert prof == {"type": "css", "value": "#login"}

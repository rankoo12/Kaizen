from __future__ import annotations

from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler
from engine.core.config.container import InMemoryStorage


class _FakeBrowser:
    async def open(self, url: str):
        return None

    async def click(self, locator):
        return None


class _OneResolver(IElementResolver):
    def resolve(self, query, snapshot):
        return {"primary": {"type": "css", "value": "#go", "visible": True, "enabled": True}, "fallbacks": [], "confidence": 1.0, "reason": "stub"}

    def find(self, target: dict):
        return [{"type": "css", "value": "#go", "visible": True, "enabled": True}]


class _S:
    HEALER_ENABLED = False
    ALLOWED_URL_SCHEMES = ["https://", "about:blank", "data:"]


def test_profile_saved_with_registrable_domain():
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
        {"tool": "open", "args": {"url": "https://app.example.co.uk/path"}},
        {"tool": "click", "args": {"target": {"css": "#go"}}},
    ]

    class _Ctx:
        run_id = "r-x"
        timeout_ms = None

    execu.execute(plan, ctx=_Ctx())
    prof = storage.find_locator_profile(domain="example.co.uk", tool="click", target_signature={})
    assert prof == {"type": "css", "value": "#go"}

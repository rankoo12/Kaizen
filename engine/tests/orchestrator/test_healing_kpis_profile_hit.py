from __future__ import annotations

from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler
from engine.core.healing.selector_healer import DeterministicHealer
from engine.core.reporting.reporter import InMemoryRunReporter


class _FailResolver(IElementResolver):
    def resolve(self, query, snapshot):
        return {"primary": None, "fallbacks": [], "confidence": 0.0, "reason": "none"}

    def find(self, target: dict):
        return []


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


class _Storage:
    def __init__(self):
        self.saved = []

    def start_run(self, test_id: str) -> str:
        return f"run-{test_id}"

    def finish_run(self, run_id: str) -> None:
        pass

    def find_locator_profile(self, *, domain, tool: str, target_signature: dict):
        # Always return a profile for click
        if tool == "click":
            return {"type": "css", "value": "#login"}
        return None


class _S:
    HEALER_ENABLED = True
    HEALER_PATH = "deterministic"
    ALLOWED_URL_SCHEMES = ["about:blank", "data:"]


def test_orchestrator_counts_profile_hits():
    browser = _FakeBrowser()
    storage = _Storage()
    healer = DeterministicHealer(storage=storage)
    execu = DeterministicPlanExecutor(
        browser=browser,
        handlers={"open": OpenHandler(browser), "click": ClickHandler(browser)},
        resolver=_FailResolver(),
        settings=_S(),
        healer=healer,
        storage=storage,
    )
    rep = InMemoryRunReporter()
    orch = EngineOrchestrator(
        planner=None,
        plan_executor=execu,
        snapshot_runner=None,
        storage=storage,
        log=None,
        reporter=rep,
        llm=None,
        settings=_S(),
    )

    class Spec:
        id = "p1"
        steps = [type("S", (), {"text": "click Login"})()]

    orch.run_live(Spec())
    stats = rep._runs[-1]["stats"]
    assert stats["profile_hits"] >= 1

from __future__ import annotations

import asyncio

from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.commands.handlers.open import OpenHandler
from engine.core.commands.handlers.click import ClickHandler
from engine.core.commands.handlers.type import TypeHandler
from engine.core.commands.handlers.press import PressHandler
from engine.core.resolving.element_resolver import ElementResolver


class _FakeLLM:
    def ask(self, prompt: str) -> str:
        # Return invalid JSON to force glue fallback
        return "not-json: please just press enter"


class _FakeBrowser:
    def __init__(self) -> None:
        self.opened = []
        self.pressed = []
        self.clicked = []
        self.typed = []

    async def open(self, url: str):
        self.opened.append(url)

    async def click(self, selector):
        self.clicked.append(selector)

    async def type(self, selector, text: str, clear: bool = False):
        self.typed.append((selector, text))

    async def press(self, key: str):
        self.pressed.append(key)

    async def screenshot(self, path: str):
        pass

    async def frames(self):
        return []

    async def evaluate(self, script: str):
        return None

    async def scroll(self, x: int, y: int):
        pass


class _FakeStorage:
    def start_run(self, test_id: str) -> str:
        return f"run-{test_id}"

    def finish_run(self, run_id: str) -> None:
        pass


class _FakeSettings:
    PLANNER_PATH = "llm"
    ALLOWED_URL_SCHEMES = ["about:blank", "data:"]


def test_live_llm_guardrails_fallback_to_glue_mapping():
    browser = _FakeBrowser()
    handlers = {
        "open": OpenHandler(browser),
        "click": ClickHandler(browser),
        "type": TypeHandler(browser),
        "press": PressHandler(browser),
    }
    execu = DeterministicPlanExecutor(
        browser=browser,
        handlers=handlers,
        resolver=ElementResolver(),
        settings=_FakeSettings(),
    )
    orch = EngineOrchestrator(
        planner=None,  # not used for glue fallback
        plan_executor=execu,
        snapshot_runner=None,  # not used
        storage=_FakeStorage(),
        validator=None,
        log=None,
        reporter=None,
        llm=_FakeLLM(),
        settings=_FakeSettings(),
    )
    spec = {"id": "t-live", "steps": [{"text": "press Enter"}]}
    run_id = orch.run_live(spec, url="about:blank")
    assert isinstance(run_id, str) and run_id.startswith("run-")
    # Verify glue mapping executed since LLM response was invalid JSON
    assert "about:blank" in browser.opened
    assert "Enter" in browser.pressed

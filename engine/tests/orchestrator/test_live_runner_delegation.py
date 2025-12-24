import asyncio

from engine.core.orchestrator.live_runner import LiveRunner
from engine.core.orchestrator.types import IOrchestrator


class FakeOrchestrator(IOrchestrator):
    def __init__(self):
        self.calls = []

    def run_snapshot(self, spec, *, html_path=None, html=None, snapshot_path=None) -> str:
        raise NotImplementedError

    def run_live(self, spec, *, url=None) -> str:
        self.calls.append((spec, url))
        return "run-XYZ"


class _FakeBrowser:
    async def open(self, url: str) -> None: ...
    async def click(self, locator): ...
    async def type(self, locator, text: str, clear: bool = False): ...
    async def press(self, key: str): ...
    async def screenshot(self, path: str): ...
    async def frames(self): ...
    async def evaluate(self, script: str): ...
    async def scroll(self, x: int, y: int): ...
    async def close(self): ...


class _FakePlanner:
    def plan(self, step_text: str):
        class _P:
            target_query = {"text": step_text}

        return _P()


class _FakeStorage:
    def start_run(self, test_id):
        return f"run-{test_id}"

    def record_step(self, step):
        pass

    def finish_run(self, run_id):
        pass


class _FakeLog:
    def info(self, msg: str, **kv):
        pass


def test_live_runner_delegates_to_orchestrator():
    orchestrator = FakeOrchestrator()
    runner = LiveRunner(
        planner=_FakePlanner(),
        browser=_FakeBrowser(),
        storage=_FakeStorage(),
        log=_FakeLog(),
        orchestrator=orchestrator,
    )

    class Spec:
        id = "demo"
        steps = []

    run_id = runner.run_sync(Spec())

    assert run_id == "run-XYZ"
    assert len(orchestrator.calls) == 1

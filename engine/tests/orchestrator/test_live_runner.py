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
        return "run-demo"


class _FakeLog:
    def info(self, msg: str, **kv):
        pass


def test_live_runner_delegates_async():
    orch = FakeOrchestrator()
    runner = LiveRunner(
        planner=None,
        browser=None,
        storage=None,
        log=_FakeLog(),
        orchestrator=orch,
    )

    class Spec:
        id = "demo-1"
        steps = []

    run_id = asyncio.run(runner.run(Spec()))

    assert run_id == "run-demo"
    assert len(orch.calls) == 1

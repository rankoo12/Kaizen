from __future__ import annotations

from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.storage.memory import InMemoryStorage


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
        # Return empty results; orchestrator should still persist stats
        return []


def test_run_live_persists_stats_in_memory_storage():
    storage = InMemoryStorage()
    ex = _FakeExecutor()
    orch = EngineOrchestrator(
        planner=None,
        plan_executor=ex,
        snapshot_runner=None,
        storage=storage,
        log=None,
        reporter=None,
        llm=None,
    )

    class Spec:
        id = "persist1"
        steps = []

    run_id = orch.run_live(Spec())
    rec = storage._runs.get(run_id)
    assert rec is not None and "stats" in rec and isinstance(rec["stats"], dict)

from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.commands.action_handler import StepResult


class _Reporter:
    def __init__(self):
        self.finish_stats = []
        self.starts = []

    def on_run_start(self, run_id: str, mode: str, **kv):
        self.starts.append((run_id, mode, kv))

    def on_run_finish(self, run_id: str, stats: dict):
        self.finish_stats.append((run_id, stats))

    def on_finish(self, run_id: str):
        pass

    def on_step(self, payload: dict):
        pass


class _SnapshotRunner:
    def run(self, spec, html_path=None, html=None, snapshot_path=None):
        return f"run-{getattr(spec, 'id', 'x')}"


class _Planner:
    def plan(self, step_text: str):
        class _P:
            target_query = {"text": step_text}

        return _P()


def test_snapshot_stats_parity_no_healing():
    rep = _Reporter()

    class _Exec:
        def execute(self, plan, *, ctx):
            return []

        def get_last_heal_stats(self):
            return {"healer": "none", "heal_attempts": 0, "heal_successes": 0, "healed_rate": 0.0}

    orch = EngineOrchestrator(
        planner=_Planner(),
        plan_executor=_Exec(),
        snapshot_runner=_SnapshotRunner(),
        storage=None,
        log=None,
        reporter=rep,
    )

    class Spec:
        id = "snap-gov-1"
        steps = []

    run_id = orch.run_snapshot(Spec())
    assert rep.finish_stats and rep.finish_stats[0][0] == run_id
    stats = rep.finish_stats[0][1]
    assert stats["planner"] == "glue" and stats["planner_fallbacks"] == 0
    assert stats["healer"] == "none" and stats["heal_attempts"] == 0 and stats["heal_successes"] == 0
    assert "reasons" in stats and isinstance(stats["reasons"], dict)


def test_snapshot_stats_parity_with_heal_counters():
    rep = _Reporter()

    class _Exec:
        def execute(self, plan, *, ctx):
            return [StepResult(ok=True, reason=None)]

        def get_last_heal_stats(self):
            return {"healer": "deterministic", "heal_attempts": 2, "heal_successes": 1, "healed_rate": 0.5}

    orch = EngineOrchestrator(
        planner=_Planner(),
        plan_executor=_Exec(),
        snapshot_runner=_SnapshotRunner(),
        storage=None,
        log=None,
        reporter=rep,
    )

    class Spec:
        id = "snap-gov-2"
        steps = []

    run_id = orch.run_snapshot(Spec())
    stats = rep.finish_stats[0][1]
    assert stats["planner"] == "glue" and stats["planner_fallbacks"] == 0
    assert stats["healer"] == "deterministic" and stats["heal_attempts"] == 2 and stats["heal_successes"] == 1
    assert 0.0 <= stats["healed_rate"] <= 1.0

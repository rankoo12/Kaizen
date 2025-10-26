from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult


class _Reporter:
    def __init__(self):
        self.finish = []

    def on_run_start(self, run_id: str, mode: str, **kw):
        pass

    def on_run_finish(self, run_id: str, stats: dict):
        self.finish.append(stats)

    def on_finish(self, run_id: str):
        pass

    def on_step(self, step_run: dict):
        pass


class _Storage:
    def start_run(self, test_id):
        return f"run-{test_id}"

    def finish_run(self, run_id):
        pass


class OkHandler(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


def _make_executor(handlers, resolver=None, settings=None, healer=None, llm=None):
    from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor

    return DeterministicPlanExecutor(
        handlers=handlers,
        resolver=resolver,
        settings=settings,
        healer=healer,
        llm=llm,
    )


class _Planner:
    def plan(self, step_text: str):
        class _P:
            target_query = {"text": step_text}

        return _P()


def test_stats_no_healing():
    rep = _Reporter()
    orch = EngineOrchestrator(
        planner=_Planner(),
        plan_executor=_make_executor(handlers={"open": OkHandler()}),
        snapshot_runner=None,
        storage=_Storage(),
        log=None,
        reporter=rep,
    )

    class Spec:
        id = "g1"
        steps = []

    orch.run_live(Spec())
    stats = rep.finish[0]
    assert stats["healer"] == "none"
    assert stats["heal_attempts"] == 0 and stats["heal_successes"] == 0
    assert stats["healed_rate"] == 0.0


def test_stats_deterministic_heal_success():
    rep = _Reporter()

    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "deterministic"

    from engine.core.healing.selector_healer import DeterministicHealer

    orch = EngineOrchestrator(
        planner=_Planner(),
        plan_executor=_make_executor(
            handlers={"open": OkHandler(), "click": OkHandler()},
            resolver=Resolver(),
            settings=_S(),
            healer=DeterministicHealer(),
        ),
        snapshot_runner=None,
        storage=_Storage(),
        log=None,
        reporter=rep,
    )

    class Spec:
        id = "g2"
        steps = [type("S", (), {"text": "click Login"})()]

    orch.run_live(Spec())
    stats = rep.finish[0]
    assert stats["healer"] in ("deterministic", "llm")  # must be at least deterministic
    assert stats["heal_attempts"] >= 1 and stats["heal_successes"] >= 1
    assert stats["healed_rate"] > 0


def test_stats_llm_then_fallback_counts():
    rep = _Reporter()

    class Resolver:
        def find(self, target: dict):
            return []

    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "llm"

    class BadLLM:
        def ask(self, prompt: str) -> str:
            return "not json"

    from engine.core.healing.selector_healer import DeterministicHealer

    orch = EngineOrchestrator(
        planner=_Planner(),
        plan_executor=_make_executor(
            handlers={"open": OkHandler(), "click": OkHandler()},
            resolver=Resolver(),
            settings=_S(),
            healer=DeterministicHealer(),
            llm=BadLLM(),
        ),
        snapshot_runner=None,
        storage=_Storage(),
        log=None,
        reporter=rep,
    )

    class Spec:
        id = "g3"
        steps = [type("S", (), {"text": "click Login"})()]

    orch.run_live(Spec())
    stats = rep.finish[0]
    # llm attempted then deterministic fallback
    assert stats["healer"] == "llm"
    assert stats["heal_attempts"] >= 2  # llm try + deterministic fallback
    assert stats["heal_successes"] >= 1
    assert 0 < stats["healed_rate"] <= 1.0

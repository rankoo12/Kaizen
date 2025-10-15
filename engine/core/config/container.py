from dependency_injector import containers, providers
from engine.core.config.settings import Settings
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.orchestrator.types import IPlanner, IResolveSnapshot


# Temporary stub for planner until integrated with real parsing logic
class SimplePlanner(IPlanner):
    def plan(self, step_text: str):
        from engine.core.orchestrator.types import StepPlan

        return StepPlan(target_query={"text": step_text})


def build_container() -> "Container":
    return Container()


class StdoutLogger:
    def info(self, msg: str, **kv):
        print(f"[INFO] {msg}", kv)

    def warn(self, msg: str, **kv):
        print(f"[WARN] {msg}", kv)

    def error(self, msg: str, **kv):
        print(f"[ERROR] {msg}", kv)


class InMemoryStorage:
    def start_run(self, test_id):
        return f"run-{test_id}"

    def record_step(self, step):
        pass

    def finish_run(self, run_id):
        pass


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["engine"])
    logger = providers.Singleton(StdoutLogger)
    settings = providers.Singleton(Settings)
    element_resolver = providers.Factory(ElementResolver)

    # TODO: replace with actual resolve_snapshot service
    resolve_snapshot = providers.Factory(
        lambda: lambda **kwargs: {"candidates": [], "reason": "stub"}
    )

    planner = providers.Singleton(SimplePlanner)

    # TODO: replace with actual storage when implemented
    storage = providers.Singleton(InMemoryStorage)

    snapshot_runner = providers.Factory(
        SnapshotRunner,
        planner=planner,
        resolve_snapshot=resolve_snapshot,
        storage=storage,
        log=logger,
    )

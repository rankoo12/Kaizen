from .types import IPlanner, IResolveSnapshot, StepPlan
from engine.core.logging.log import ILog


class SnapshotRunner:
    def __init__(
        self, planner: IPlanner, resolve_snapshot: IResolveSnapshot, storage, log: ILog
    ):
        self._planner = planner
        self._resolve_snapshot = resolve_snapshot
        self._storage = storage
        self._log = log

    def run(
        self, spec, *, html: str | None = None, snapshot_path: str | None = None
    ) -> str:
        self._log.info("Starting snapshot run", test_id=spec.id)
        run_id = self._storage.start_run(test_id=spec.id)

        for i, step in enumerate(spec.steps):
            plan: StepPlan = self._planner.plan(step.text)
            result = self._resolve_snapshot(
                html=html,
                snapshot_path=snapshot_path,
                target_query=plan.target_query,
            )
            self._storage.record_step(
                {
                    "run_id": run_id,
                    "index": i,
                    "result": result,
                }
            )
            self._log.info("Step completed", index=i, reason=result.get("reason"))

        self._storage.finish_run(run_id)
        self._log.info("Snapshot run finished", run_id=run_id)
        return run_id

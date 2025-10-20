from __future__ import annotations

from typing import Any, Callable

from engine.core.orchestrator.types import IOrchestrator, IPlanner, IPlanExecutor
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.validation.plan_validator import validate_plan as _validate_plan
from engine.core.logging.log import ILog
from engine.core.commands.action_handler import ExecCtx


class EngineOrchestrator(IOrchestrator):
    """
    High-level coordinator that owns planning/validation and delegates execution
    to runners or the plan executor as appropriate.

    Initial implementation keeps existing runners intact to avoid behavior
    changes; later we can route live execution through the plan executor.
    """

    def __init__(
        self,
        *,
        planner: IPlanner,
        plan_executor: IPlanExecutor,
        snapshot_runner: SnapshotRunner,
        storage,
        validator: Callable[[Any], None] | None = None,
        log: ILog | None = None,
    ) -> None:
        self._planner = planner
        self._executor = plan_executor
        self._snapshot_runner = snapshot_runner
        self._storage = storage
        self._validate = validator or _validate_plan
        self._log = log

    def run_snapshot(
        self,
        spec: Any,
        *,
        html_path: str | None = None,
        html: str | None = None,
        snapshot_path: str | None = None,
    ) -> str:
        # Snapshot stays fully deterministic/offline via existing runner
        return self._snapshot_runner.run(
            spec,
            html_path=html_path,
            html=html,
            snapshot_path=snapshot_path,
        )

    def run_live(self, spec: Any, *, url: str | None = None) -> str:
        # Start run and log
        test_id = getattr(spec, "id", "unknown")
        if hasattr(self._storage, "start_run"):
            run_id = self._storage.start_run(test_id=test_id)
        else:
            run_id = f"run-{test_id}"
        if self._log:
            self._log.info("orchestrator.live.start", test_id=test_id, run_id=run_id)

        # Build a minimal deterministic plan: open a safe URL first
        target_url = url or "about:blank"
        plan: list[dict] = [
            {"tool": "open", "args": {"url": target_url}},
        ]

        # Optional: later, extend with per-step conversions
        # Validate and execute
        self._validate(plan)
        ctx = ExecCtx(run_id=run_id)
        _ = self._executor.execute(plan, ctx=ctx)

        # Finish run and log
        if hasattr(self._storage, "finish_run"):
            self._storage.finish_run(run_id)
        if self._log:
            self._log.info("orchestrator.live.finish", run_id=run_id)
        return run_id

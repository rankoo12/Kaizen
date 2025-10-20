from __future__ import annotations

from typing import Any, Callable

from engine.core.orchestrator.types import IOrchestrator, IPlanner, IPlanExecutor
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.validation.plan_validator import validate_plan as _validate_plan
from engine.core.logging.log import ILog
from engine.core.commands.action_handler import ExecCtx
from engine.core.reporting.reporter import IReporter
from engine.core.types.dtos import StepSpec


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
        reporter: IReporter | None = None,
    ) -> None:
        self._planner = planner
        self._executor = plan_executor
        self._snapshot_runner = snapshot_runner
        self._storage = storage
        self._validate = validator or _validate_plan
        self._log = log
        self._reporter = reporter

    def run_snapshot(
        self,
        spec: Any,
        *,
        html_path: str | None = None,
        html: str | None = None,
        snapshot_path: str | None = None,
    ) -> str:
        # Snapshot stays fully deterministic/offline via existing runner
        run_id = self._snapshot_runner.run(
            spec,
            html_path=html_path,
            html=html,
            snapshot_path=snapshot_path,
        )
        if self._reporter:
            self._reporter.on_run_start(run_id, mode="snapshot")

        # Optionally execute simple post-load steps via executor (no navigation)
        steps = getattr(spec, "steps", []) or []
        results = []
        if steps:
            plan: list[dict] = [{"tool": "open", "args": {"url": "about:blank"}}]
            for s in steps:
                text = getattr(s, "text", None) if hasattr(s, "text") else None
                if not text or not isinstance(text, str):
                    continue
                lower = text.strip().lower()
                if lower.startswith("press "):
                    key = text.split(" ", 1)[1].strip()
                    plan.append({"tool": "press", "args": {"key": key}})
            if len(plan) > 1:
                self._validate(plan)
                ctx = ExecCtx(run_id=run_id)
                results = self._executor.execute(plan, ctx=ctx)

        # Reporter run-finish events with minimal stats
        if self._reporter:
            total = len(results)
            passed = sum(1 for r in results if getattr(r, "ok", False))
            failed = total - passed
            stats = {"total": total, "passed": passed, "failed": failed}
            self._reporter.on_run_finish(run_id, stats)
            self._reporter.on_finish(run_id)
        return run_id

    def run_live(self, spec: Any, *, url: str | None = None) -> str:
        # Start run and log
        test_id = getattr(spec, "id", "unknown")
        if hasattr(self._storage, "start_run"):
            run_id = self._storage.start_run(test_id=test_id)
        else:
            run_id = f"run-{test_id}"
        if self._log:
            self._log.info("orchestrator.live.start", test_id=test_id, run_id=run_id)
        if self._reporter:
            self._reporter.on_run_start(run_id, mode="live")

        # Build a minimal deterministic plan: open a safe URL first
        target_url = url or "about:blank"
        plan: list[dict] = [
            {"tool": "open", "args": {"url": target_url}},
        ]

        # Minimal conversion of spec steps into ToolCalls (offline-safe)
        steps = getattr(spec, "steps", []) or []
        for s in steps:
            text = None
            if isinstance(s, dict):
                text = s.get("text")
            else:
                text = getattr(s, "text", None) if hasattr(s, "text") else None
            if not text or not isinstance(text, str):
                continue
            lower = text.strip().lower()
            if lower.startswith("click "):
                raw = text.split(" ", 1)[1].strip() or ""
                # Prefer structured CSS target when user specifies #id or .class
                if raw.startswith("#") or raw.startswith("."):
                    target = {"css": raw}
                else:
                    target = {"text": raw}
                plan.append({"tool": "click", "args": {"target": target}})
            elif lower.startswith("type "):
                typed = text.split(" ", 1)[1].strip()
                plan.append({
                    "tool": "type",
                    "args": {"target": {"text": "input"}, "text": typed},
                })
            elif lower.startswith("press "):
                key = text.split(" ", 1)[1].strip()
                plan.append({
                    "tool": "press",
                    "args": {"key": key},
                })

        # Validate and execute
        self._validate(plan)
        ctx = ExecCtx(run_id=run_id)
        results = self._executor.execute(plan, ctx=ctx)

        # Finish run and log
        if hasattr(self._storage, "finish_run"):
            self._storage.finish_run(run_id)
        # Aggregate minimal stats
        total = len(results)
        passed = sum(1 for r in results if getattr(r, "ok", False))
        failed = total - passed
        stats = {"total": total, "passed": passed, "failed": failed}
        if self._reporter:
            self._reporter.on_run_finish(run_id, stats)
            self._reporter.on_finish(run_id)
        if self._log:
            self._log.info("orchestrator.live.finish", run_id=run_id)
        return run_id

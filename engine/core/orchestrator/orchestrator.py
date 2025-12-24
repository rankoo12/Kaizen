from __future__ import annotations

from typing import Any, Callable

from engine.core.orchestrator.types import IOrchestrator, IPlanner, IPlanExecutor
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.validation.plan_validator import validate_plan as _validate_plan
from engine.core.logging.log import ILog
from engine.core.commands.action_handler import ExecCtx
from engine.core.reporting.reporter import IReporter
from engine.core.llm.text_llm import ILLMText
from engine.core.config.settings import Settings, settings as _settings
from engine.core.llm.intent_prompt import build_intent_prompt
from engine.core.planning.planner import PlannerService


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
        llm: ILLMText | None = None,
        settings: Settings = _settings,
    ) -> None:
        self._planner = planner
        self._executor = plan_executor
        self._snapshot_runner = snapshot_runner
        self._storage = storage
        self._validate = validator or _validate_plan
        self._log = log
        self._reporter = reporter
        self._llm = llm
        self._settings = settings

    def _llm_parse_intent(self, text: str, tool: str | None = None) -> dict:
        if self._llm is None or not isinstance(text, str) or not text.strip():
            return {}
        try:
            prompt = build_intent_prompt(text, tool)
            raw = self._llm.ask(prompt)
        except Exception:
            return {}
        try:
            import json

            data = json.loads(raw)
        except Exception:
            try:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    import json

                    data = json.loads(raw[start:end])
                else:
                    return {}
            except Exception:
                return {}
        if not isinstance(data, dict):
            return {}
        out: dict = {}
        noun = data.get("noun")
        if isinstance(noun, str) and noun.strip():
            out["noun"] = noun.strip()
        ordinal = data.get("ordinal")
        position = data.get("position")
        if isinstance(position, str) and position.strip().lower() in {"last", "final"}:
            out["position"] = "last"
        else:
            if isinstance(ordinal, str):
                ordinal = ordinal.strip()
                if ordinal:
                    try:
                        ordinal = int(ordinal)
                    except Exception:
                        ordinal = None
            if isinstance(ordinal, int) and ordinal != 0:
                out["ordinal"] = ordinal
        return out

    def _extract_test_meta(self, spec: Any) -> tuple[str, dict]:
        if isinstance(spec, dict):
            test_id = str(spec.get("id") or spec.get("name") or "unknown")
            extra_fields = {}
            try:
                if isinstance(spec.get("fields"), dict):
                    extra_fields = dict(spec["fields"])  # type: ignore[arg-type]
            except Exception:
                extra_fields = {}
            return test_id, extra_fields
        test_id = getattr(spec, "id", "unknown")
        return str(test_id), {}

    def _extract_steps(self, spec: Any) -> list:
        try:
            if isinstance(spec, dict):
                return list(spec.get("steps") or [])
            return list(getattr(spec, "steps", []) or [])
        except Exception:
            return []

    def _extract_step_text(self, step: Any) -> str | None:
        if isinstance(step, dict):
            return step.get("text")
        return getattr(step, "text", None) if hasattr(step, "text") else None

    def _select_target_url(self, spec: Any, url: str | None) -> str:
        if url:
            return url
        try:
            if isinstance(spec, dict):
                return (
                    spec.get("app_base_url")
                    or spec.get("website")
                    or spec.get("url")
                    or "about:blank"
                )
            return (
                getattr(spec, "app_base_url", None)
                or getattr(spec, "website", None)
                or getattr(spec, "url", None)
                or "about:blank"
            )
        except Exception:
            return "about:blank"

    def _build_run_logger(self, run_id: str):
        if self._log and hasattr(self._log, "run_logger"):
            try:
                return self._log.run_logger(run_id=run_id)  # type: ignore[attr-defined]
            except Exception:
                return None
        return None

    def _emit_run_start(
        self,
        run_id: str,
        *,
        test_id: str,
        planner_path: str,
        extra_fields: dict,
        run_logger=None,
    ) -> None:
        extra = {}
        try:
            if getattr(self._settings, "SBOM_REF", None):
                extra["sbom_ref"] = self._settings.SBOM_REF
        except Exception:
            pass
        if run_logger or self._log:
            try:
                (run_logger or self._log).info(
                    "orchestrator.live.start", test_id=test_id, run_id=run_id, **extra
                )  # type: ignore[operator]
            except Exception:
                pass
        if self._reporter:
            self._reporter.on_run_start(
                run_id,
                mode="live",
                planner=planner_path,
                planner_fallbacks=0,
                healer="none",
                heal_attempts=0,
                **(extra_fields or {}),
            )

    def _build_live_plan(
        self,
        *,
        steps: list,
        target_url: str,
        planner_path: str,
        run_logger=None,
    ) -> tuple[list[dict], int]:
        plan: list[dict] = [{"tool": "open", "args": {"url": target_url}}]
        fallback_count = 0
        planner = PlannerService(llm=self._llm, settings=self._settings)
        llm_intent_resolver = (
            self._llm_parse_intent if (planner_path == "llm" and self._llm is not None) else None
        )

        for idx, step in enumerate(steps):
            text = self._extract_step_text(step)
            if not text or not isinstance(text, str):
                continue
            before_len = len(plan)
            step_plan: list[dict] | None = None
            if planner_path == "llm" and self._llm is not None:
                try:
                    step_plan = planner.llm_plan(text, context=None)
                    if step_plan is not None:
                        self._validate(step_plan)
                except Exception:
                    step_plan = None
                if step_plan is None:
                    fallback_count += 1
            if step_plan is None:
                step_plan = planner.glue_plan(
                    text, llm_intent_resolver=llm_intent_resolver
                )
            plan.extend(step_plan)
            if run_logger is not None and len(plan) > before_len:
                try:
                    step_tools = plan[before_len:]
                    run_logger.info(
                        "planner.step",
                        step_index=idx,
                        text=text,
                        planner_path=planner_path,
                        tools=step_tools,
                    )
                except Exception:
                    pass
        return plan, fallback_count

    def _execute_plan(self, plan: list[dict], *, run_id: str, run_logger=None):
        ctx = ExecCtx(run_id=run_id)
        _prev_exec_log = getattr(self._executor, "_log", None)
        try:
            if run_logger is not None:
                try:
                    self._executor._log = run_logger  # type: ignore[attr-defined]
                except Exception:
                    pass
            return self._executor.execute(plan, ctx=ctx)
        finally:
            try:
                self._executor._log = _prev_exec_log  # type: ignore[attr-defined]
            except Exception:
                pass

    def _aggregate_stats(
        self, results: list, *, planner_path: str, fallback_count: int
    ) -> dict:
        total = len(results)
        passed = sum(1 for r in results if getattr(r, "ok", False))
        failed = total - passed
        reasons: dict[str, int] = {}
        for r in results:
            key = getattr(r, "reason", None) or "none"
            reasons[key] = reasons.get(key, 0) + 1
        heal_stats = {}
        try:
            heal_stats = self._executor.get_last_heal_stats() or {}
        except Exception:
            heal_stats = {}
        llm_stats = {}
        try:
            llm_stats = self._executor.get_last_llm_stats() or {}
        except Exception:
            llm_stats = {}
        stats = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "reasons": reasons,
            "planner": planner_path,
            "planner_fallbacks": fallback_count,
            "healer": heal_stats.get("healer", "none"),
            "heal_attempts": heal_stats.get("heal_attempts", 0),
            "heal_successes": heal_stats.get("heal_successes", 0),
            "healed_rate": heal_stats.get("healed_rate", 0.0),
            "profile_hits": int(heal_stats.get("profile_hits", 0) or 0),
            "profile_misses": int(heal_stats.get("profile_misses", 0) or 0),
        }
        try:
            stats["llm_prompt_tokens"] = int(
                llm_stats.get("llm_prompt_tokens", 0) or 0
            )
            stats["llm_completion_tokens"] = int(
                llm_stats.get("llm_completion_tokens", 0) or 0
            )
            stats["llm_total_tokens"] = int(
                llm_stats.get("llm_total_tokens", 0) or 0
            )
        except Exception:
            pass
        return stats

    def _emit_run_finish(
        self,
        run_id: str,
        *,
        planner_path: str,
        fallback_count: int,
        run_logger=None,
    ) -> None:
        if run_logger or self._log:
            extra = {"planner": planner_path, "planner_fallbacks": fallback_count}
            try:
                if getattr(self._settings, "SBOM_REF", None):
                    extra["sbom_ref"] = self._settings.SBOM_REF
            except Exception:
                pass
            try:
                (run_logger or self._log).info(
                    "orchestrator.live.finish", run_id=run_id, **extra
                )  # type: ignore[operator]
            except Exception:
                pass

    def run_snapshot(
        self,
        spec: Any,
        *,
        html_path: str | None = None,
        html: str | None = None,
        snapshot_path: str | None = None,
    ) -> str:
        # Snapshot stays fully deterministic/offline via existing runner
        # Guard the snapshot runner to avoid failing the entire run in constrained envs
        try:
            run_id = self._snapshot_runner.run(
                spec,
                html_path=html_path,
                html=html,
                snapshot_path=snapshot_path,
            )
        except Exception:
            import time as _time

            run_id = f"run-error-{int(_time.time())}"
            if self._reporter:
                # Emit minimal start/finish so observers have a stable record
                self._reporter.on_run_start(
                    run_id,
                    mode="snapshot",
                    planner="glue",
                    planner_fallbacks=0,
                    healer="none",
                    heal_attempts=0,
                )
                self._reporter.on_run_finish(
                    run_id,
                    {
                        "total": 0,
                        "passed": 0,
                        "failed": 1,
                        "reasons": {"runner_error": 1},
                        "planner": "glue",
                        "planner_fallbacks": 0,
                        "healer": "none",
                        "heal_attempts": 0,
                        "heal_successes": 0,
                        "healed_rate": 0.0,
                        "redactions": [],
                    },
                )
                self._reporter.on_finish(run_id)
            return run_id
        if self._reporter:
            self._reporter.on_run_start(
                run_id,
                mode="snapshot",
                planner="glue",
                planner_fallbacks=0,
                healer="none",
                heal_attempts=0,
            )

        # Optionally execute simple post-load steps via executor (no navigation)
        steps = []
        try:
            if isinstance(spec, dict):
                steps = spec.get("steps") or []
            else:
                steps = getattr(spec, "steps", []) or []
        except Exception:
            steps = []
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
                try:
                    self._validate(plan)
                    ctx = ExecCtx(run_id=run_id)
                    results = self._executor.execute(plan, ctx=ctx)
                except Exception:
                    # Keep snapshot path deterministic even if executor is unavailable (e.g., no browser)
                    results = []

        # Reporter run-finish events with minimal stats + healing stats
        if self._reporter:
            total = len(results)
            passed = sum(1 for r in results if getattr(r, "ok", False))
            failed = total - passed
            reasons: dict[str, int] = {}
            for r in results:
                key = getattr(r, "reason", None) or "none"
                reasons[key] = reasons.get(key, 0) + 1
            heal_stats = {}
            try:
                heal_stats = self._executor.get_last_heal_stats() or {}
            except Exception:
                heal_stats = {}
            stats = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "reasons": reasons,
                # snapshot defaults for planner fields
                "planner": "glue",
                "planner_fallbacks": 0,
                "healer": heal_stats.get("healer", "none"),
                "heal_attempts": heal_stats.get("heal_attempts", 0),
                "heal_successes": heal_stats.get("heal_successes", 0),
                "healed_rate": max(
                    0.0, min(1.0, float(heal_stats.get("healed_rate", 0.0) or 0.0))
                ),
                "profile_hits": int(heal_stats.get("profile_hits", 0) or 0),
                "profile_misses": int(heal_stats.get("profile_misses", 0) or 0),
                "redactions": [],
            }
            self._reporter.on_run_finish(run_id, stats)
            self._reporter.on_finish(run_id)
        # Persist run stats to storage when available
        try:
            if hasattr(self._storage, "finish_run"):
                self._storage.finish_run(run_id, stats)
        except Exception:
            pass
        return run_id

    def run_live(self, spec: Any, *, url: str | None = None) -> str:
        test_id, extra_fields = self._extract_test_meta(spec)
        if hasattr(self._storage, "start_run"):
            run_id = self._storage.start_run(test_id=test_id)
        else:
            run_id = f"run-{test_id}"
        run_logger = self._build_run_logger(run_id)
        planner_path = (
            getattr(self._settings, "PLANNER_PATH", "glue")
            if hasattr(self, "_settings") and self._settings
            else "glue"
        )
        self._emit_run_start(
            run_id,
            test_id=test_id,
            planner_path=planner_path,
            extra_fields=extra_fields,
            run_logger=run_logger,
        )

        target_url = self._select_target_url(spec, url)
        steps = self._extract_steps(spec)
        plan, fallback_count = self._build_live_plan(
            steps=steps,
            target_url=target_url,
            planner_path=planner_path,
            run_logger=run_logger,
        )

        # Validate and execute.
        self._validate(plan)
        results = self._execute_plan(plan, run_id=run_id, run_logger=run_logger)

        stats = self._aggregate_stats(
            results, planner_path=planner_path, fallback_count=fallback_count
        )
        if self._reporter:
            self._reporter.on_run_finish(run_id, stats)
            self._reporter.on_finish(run_id)
        try:
            if hasattr(self._storage, "finish_run"):
                self._storage.finish_run(run_id, stats)
        except Exception:
            pass
        self._emit_run_finish(
            run_id,
            planner_path=planner_path,
            fallback_count=fallback_count,
            run_logger=run_logger,
        )
        return run_id

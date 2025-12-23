from __future__ import annotations

from typing import Any, Callable
import re

from engine.core.orchestrator.types import IOrchestrator, IPlanner, IPlanExecutor
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.validation.plan_validator import validate_plan as _validate_plan
from engine.core.logging.log import ILog
from engine.core.commands.action_handler import ExecCtx
from engine.core.reporting.reporter import IReporter
from engine.core.llm.text_llm import ILLMText
from engine.core.config.settings import Settings, settings as _settings
from engine.core.types.dtos import StepSpec
from engine.core.parsing.intent import parse_intent, split_type_step
from engine.core.llm.intent_prompt import build_intent_prompt


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
        # Start run and log
        if isinstance(spec, dict):
            # Prefer contract-style id, then name; fall back to "unknown"
            test_id = str(spec.get("id") or spec.get("name") or "unknown")
            # Optional per-run metadata for the reporter (e.g. suite_id)
            extra_fields = {}
            try:
                if isinstance(spec.get("fields"), dict):
                    extra_fields = dict(spec["fields"])  # type: ignore[arg-type]
            except Exception:
                extra_fields = {}
        else:
            test_id = getattr(spec, "id", "unknown")
            extra_fields = {}
        if hasattr(self._storage, "start_run"):
            run_id = self._storage.start_run(test_id=test_id)
        else:
            run_id = f"run-{test_id}"
        # Prefer a per-run JSONL logger so artifacts include a run-<id>.jsonl file
        run_logger = None
        if self._log and hasattr(self._log, "run_logger"):
            try:
                run_logger = self._log.run_logger(run_id=run_id)  # type: ignore[attr-defined]
            except Exception:
                run_logger = None
        if run_logger or self._log:
            extra = {}
            try:
                if getattr(self._settings, "SBOM_REF", None):
                    extra["sbom_ref"] = self._settings.SBOM_REF
            except Exception:
                pass
            try:
                (run_logger or self._log).info("orchestrator.live.start", test_id=test_id, run_id=run_id, **extra)  # type: ignore[operator]
            except Exception:
                pass
        # Determine planner path before emitting start event
        planner_path = (
            getattr(self._settings, "PLANNER_PATH", "glue")
            if hasattr(self, "_settings") and self._settings
            else "glue"
        )
        if self._reporter:
            self._reporter.on_run_start(
                run_id,
                mode="live",
                planner=planner_path,
                planner_fallbacks=0,
                healer="none",
                heal_attempts=0,
                **extra_fields,
            )

        # Build a minimal deterministic plan: open a safe URL first.
        # If callers didn't pass a URL, try to derive it from the spec.
        target_url = url
        if not target_url:
            try:
                if isinstance(spec, dict):
                    target_url = (
                        spec.get("app_base_url")
                        or spec.get("website")
                        or spec.get("url")
                    )
                else:
                    target_url = (
                        getattr(spec, "app_base_url", None)
                        or getattr(spec, "website", None)
                        or getattr(spec, "url", None)
                    )
            except Exception:
                target_url = None
        if not target_url:
            target_url = "about:blank"
        plan: list[dict] = [
            {"tool": "open", "args": {"url": target_url}},
        ]

        # Minimal conversion of spec steps into ToolCalls (offline-safe)
        # planner_path computed above
        fallback_count = 0
        steps = []
        try:
            if isinstance(spec, dict):
                steps = spec.get("steps") or []
            else:
                steps = getattr(spec, "steps", []) or []
        except Exception:
            steps = []
        for idx, s in enumerate(steps):
            text = None
            if isinstance(s, dict):
                text = s.get("text")
            else:
                text = getattr(s, "text", None) if hasattr(s, "text") else None
            if not text or not isinstance(text, str):
                continue
            before_len = len(plan)
            if planner_path == "llm" and self._llm is not None:
                # Use strict JSON-only prompt and validate; fallback to glue on any failure
                try:
                    import json
                    from engine.core.llm.plan_prompt import build_planner_prompt

                    prompt = build_planner_prompt(text, context=None)
                    raw = self._llm.ask(prompt)
                    try:
                        calls = json.loads(raw)
                    except Exception:
                        # heuristic: locate first '[' and last ']'
                        start = raw.find("[")
                        end = raw.rfind("]") + 1
                        if start >= 0 and end > start:
                            calls = json.loads(raw[start:end])
                        else:
                            raise
                    calls_list = calls if isinstance(calls, list) else [calls]
                    self._validate(calls_list)
                    plan.extend(calls_list)
                    continue
                except Exception:
                    fallback_count += 1
                    # fall through to glue mapping below
            # glue mapping fallback
            lower = text.strip().lower()
            # Navigation, tab/window, scroll, and basic actions
            if "go back" in lower or lower.strip() in {
                "back",
                "previous page",
                "previous screen",
            }:
                plan.append({"tool": "back", "args": {}})
            elif (
                "go forward" in lower
                or "next page" in lower
                or "next screen" in lower
                or lower.strip() in {"forward"}
            ):
                plan.append({"tool": "forward", "args": {}})
            elif "reload" in lower or "refresh" in lower:
                plan.append({"tool": "reload", "args": {}})
            elif "first tab" in lower and "switch" in lower:
                plan.append({"tool": "switchTab", "args": {"index": 0}})
            elif "new tab" in lower:
                plan.append({"tool": "newTab", "args": {}})
            elif "new window" in lower:
                plan.append({"tool": "newWindow", "args": {}})
            elif "switch to tab" in lower or "go to tab" in lower:
                m = re.search(r"tab\s+(\d+)", lower)
                if m:
                    args: dict[str, Any] = {}
                    try:
                        idx = max(int(m.group(1)) - 1, 0)
                        args["index"] = idx
                    except Exception:
                        pass
                    if args:
                        plan.append({"tool": "switchTab", "args": args})
            elif "switch to window" in lower or "go to window" in lower:
                m2 = re.search(r"window\s+(\d+)", lower)
                if m2:
                    args2: dict[str, Any] = {}
                    try:
                        idx2 = max(int(m2.group(1)) - 1, 0)
                        args2["index"] = idx2
                    except Exception:
                        pass
                    if args2:
                        plan.append({"tool": "switchWindow", "args": args2})
            elif (
                "close current tab" in lower
                or "close the current tab" in lower
                or lower.strip() in {"close tab", "close this tab"}
            ):
                plan.append({"tool": "closeTab", "args": {}})
            elif "close current window" in lower or lower.strip() in {
                "close window",
                "close this window",
            }:
                plan.append({"tool": "closeWindow", "args": {}})
            elif (
                "submit the form" in lower
                or "submit form" in lower
                or (lower.startswith("submit ") and " form" in lower)
            ):
                # Fall back to Enter key for generic form submit
                plan.append({"tool": "press", "args": {"key": "Enter"}})
            elif lower.startswith(("assert ", "check ", "verify ")):
                if "url contains" in lower:
                    m = re.search(r"url\s+contains\s+(\S+)", lower)
                    expected = None
                    if m:
                        expected = m.group(1).strip(" .'\"")
                    if expected:
                        plan.append(
                            {
                                "tool": "assertUrl",
                                "args": {"expected": expected, "match": "contains"},
                            }
                        )
                elif "'" in text or '"' in text:
                    m = re.search(r"'([^']+)'", text)
                    if not m:
                        m = re.search(r"\"([^\"]+)\"", text)
                    expected_text = m.group(1).strip() if m else ""
                    if expected_text:
                        plan.append(
                            {
                                "tool": "assertText",
                                "args": {
                                    "target": {"text": expected_text},
                                    "expected": expected_text,
                                    "match": "contains",
                                },
                            }
                        )
            elif lower.startswith("scroll"):
                direction = "down"
                if "up" in lower or "top" in lower:
                    direction = "up"
                elif "left" in lower:
                    direction = "left"
                elif "right" in lower:
                    direction = "right"
                amount = 400
                plan.append(
                    {
                        "tool": "scroll",
                        "args": {"direction": direction, "amount": amount},
                    }
                )
            elif lower.startswith("download "):
                label = text.split(" ", 1)[1].strip()
                plan.append({"tool": "download", "args": {"target": {"text": label}}})
            elif lower.startswith("click "):
                raw = text.split(" ", 1)[1].strip() or ""
                # Prefer structured CSS target when user specifies CSS-y strings
                css_like = False
                try:
                    if (
                        raw.startswith("#")
                        or raw.startswith(".")
                        or raw.startswith("[")
                    ):
                        css_like = True
                    # common tag selectors and attribute selectors
                    elif (
                        raw.split("(")[0]
                        .lower()
                        .startswith(
                            (
                                "input",
                                "button",
                                "a",
                                "label",
                                "form",
                                "textarea",
                                "select",
                            )
                        )
                    ):
                        css_like = True
                    elif "[" in raw or ":" in raw or ">" in raw or "=" in raw:
                        css_like = True
                except Exception:
                    css_like = False
                if css_like:
                    target = {"css": raw}
                else:
                    intent = parse_intent(text, tool="click")
                    if not intent:
                        intent = self._llm_parse_intent(text, tool="click")
                    noun = intent.get("noun") if isinstance(intent, dict) else None
                    target_text = noun if isinstance(noun, str) and noun else raw
                    target = {"text": target_text}
                    if intent:
                        target["__intent"] = intent
                plan.append({"tool": "click", "args": {"target": target}})
            elif lower.startswith(("type ", "enter ", "write ")):
                typed, target_phrase = split_type_step(text)
                if not typed:
                    typed = text.split(" ", 1)[1].strip()
                intent = parse_intent(target_phrase or text, tool="type")
                if not intent:
                    intent = self._llm_parse_intent(target_phrase or text, tool="type")
                noun = intent.get("noun") if isinstance(intent, dict) else None
                target_text = noun if isinstance(noun, str) and noun else "input"
                target = {"text": target_text}
                if intent:
                    target["__intent"] = intent
                plan.append(
                    {
                        "tool": "type",
                        "args": {"target": target, "text": typed},
                    }
                )
            elif lower.startswith("press "):
                key_raw = text.split(" ", 1)[1].strip()
                try:
                    from engine.core.parsing.keys import normalize_key_name

                    key = normalize_key_name(key_raw)
                except Exception:
                    key = key_raw
                plan.append({"tool": "press", "args": {"key": key}})
            # Emit planner trace for this step (per-step examples for QA dataset)
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
                    # never fail planning due to logging
                    pass

        # Validate and execute
        self._validate(plan)
        ctx = ExecCtx(run_id=run_id)
        # Temporarily route executor logs to the per-run logger so step logs land in run-<id>.jsonl
        _prev_exec_log = getattr(self._executor, "_log", None)
        try:
            if run_logger is not None:
                try:
                    self._executor._log = run_logger  # type: ignore[attr-defined]
                except Exception:
                    pass
            results = self._executor.execute(plan, ctx=ctx)
        finally:
            try:
                self._executor._log = _prev_exec_log  # type: ignore[attr-defined]
            except Exception:
                pass

        # Finish run and log
        # Aggregate minimal stats + reasons breakdown + healing stats
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
        # Aggregate PageBrain/LLM token usage when available
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
        if self._reporter:
            self._reporter.on_run_finish(run_id, stats)
            self._reporter.on_finish(run_id)
        # Persist run stats to storage when available
        try:
            if hasattr(self._storage, "finish_run"):
                self._storage.finish_run(run_id, stats)
        except Exception:
            pass
        if run_logger or self._log:
            extra = {"planner": planner_path, "planner_fallbacks": fallback_count}
            try:
                if getattr(self._settings, "SBOM_REF", None):
                    extra["sbom_ref"] = self._settings.SBOM_REF
            except Exception:
                pass
            try:
                (run_logger or self._log).info("orchestrator.live.finish", run_id=run_id, **extra)  # type: ignore[operator]
            except Exception:
                pass
        return run_id

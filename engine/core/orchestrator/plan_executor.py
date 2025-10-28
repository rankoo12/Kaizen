from __future__ import annotations

from typing import List, Any, Callable
import time
from datetime import datetime

from engine.core.orchestrator.types import IPlanExecutor, Plan
from engine.core.commands.action_handler import StepResult, ExecCtx, IActionHandler
from engine.core.logging.log import ILog
from engine.core.browser.browser_port import IBrowser
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.reporting.reporter import IReporter
from engine.core.time.clock import IClock
from engine.core.orchestrator import reasons as R
from engine.core.config.settings import Settings
from engine.core.healing.selector_healer import ISelectorHealer
from engine.core.llm.text_llm import ILLMText


class DeterministicPlanExecutor(IPlanExecutor):
    """
    Minimal, deterministic executor stub.

    For now, this does not perform real browser actions; it records the
    intention of each ToolCall and returns successful StepResult entries.
    It can be extended to use IActionHandler/IBrowser without changing callers.
    """

    def __init__(
        self,
        *,
        browser: IBrowser | None = None,
        handlers: dict[str, IActionHandler] | None = None,
        resolver: IElementResolver | None = None,
        log: ILog | None = None,
        reporter: IReporter | None = None,
        clock: IClock | None = None,
        settings: Settings | None = None,
        healer: ISelectorHealer | None = None,
        llm: ILLMText | None = None,
    ):
        self._browser = browser
        self._handlers = handlers or {}
        self._resolver = resolver
        self._log = log
        self._reporter = reporter
        self._clock = clock
        self._settings = settings
        self._max_attempts = 50
        self._healer = healer
        self._llm = llm

    def execute(self, plan: Plan, *, ctx: ExecCtx) -> List[StepResult]:
        # reset heal stats per execution
        self._heal_attempts = 0
        self._heal_successes = 0
        self._healer_mode_used = "none"
        self._llm_attempted = False
        self._det_attempted = False

        results: List[StepResult] = []
        for idx, call in enumerate(plan):
            step_start = time.time()
            tool = call.get("tool")
            args: dict[str, Any] = call.get("args", {})

            # Safety checks beyond schema
            if not tool or not isinstance(args, dict):
                res = StepResult(ok=False, reason=R.INVALID_TOOLCALL)
                results.append(res)
                self._emit_metric(tool or "<none>", res)
                try:
                    self._emit_report(ctx, idx, tool or "<none>", res, duration=(time.time() - step_start))
                except Exception:
                    pass
                continue

            if self._log:
                self._log.info(
                    "plan_step",
                    run_id=getattr(ctx, "run_id", None),
                    index=idx,
                    tool=tool,
                    args=args,
                )

            handler = self._handlers.get(tool)
            if handler is None:
                res = StepResult(ok=False, reason=R.MISSING_HANDLER)
                results.append(res)
                self._emit_metric(tool, res)
                continue

            # Enforce offline-safe open policy
            if tool == "open":
                url = args.get("url", "")
                allowed = False
                if isinstance(url, str):
                    schemes = (getattr(self._settings, "ALLOWED_URL_SCHEMES", ["data:", "about:blank"]) or [])
                    for scheme in schemes:
                        if scheme == "about:blank":
                            if url == "about:blank":
                                allowed = True
                                break
                        else:
                            if url.startswith(scheme):
                                allowed = True
                                break
                if not allowed:
                    res = StepResult(ok=False, reason=R.URL_SCHEME_NOT_ALLOWED)
                    results.append(res)
                    self._emit_report(ctx, idx, tool, res, duration=(time.time() - step_start))
                    self._emit_metric(tool, res)
                    continue

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(ctx, idx, tool, res, duration=(time.time() - step_start))
                self._emit_metric(tool, res)
                continue

            # Resolve target deterministically for interactive actions
            if tool in {"click", "type", "press"}:
                target = args.get("target")
                # press may not require a target
                requires_target = tool in {"click", "type"}
                if requires_target and not isinstance(target, dict):
                    res = StepResult(ok=False, reason=R.MISSING_TARGET)
                    results.append(res)
                    self._emit_report(ctx, idx, tool, res)
                    self._emit_metric(tool, res)
                    continue

                resolved = None
                if isinstance(target, dict) and self._resolver is not None:
                    # Prefer a 'find' method if available (duck-typing), else fallback
                    finder: Callable[[dict], Any] | None = getattr(self._resolver, "find", None)
                    if callable(finder):
                        timeout_ms = ctx.timeout_ms
                        if timeout_ms is None:
                            timeout_ms = getattr(self._settings, "EXEC_TIMEOUT_MS", None)
                        if timeout_ms is None:
                            # Legacy immediate behavior
                            try:
                                candidates = finder(target) or []
                            except Exception:
                                candidates = []
                            if len(candidates) != 1:
                                reason = R.RESOLVE_ZERO if len(candidates) == 0 else R.RESOLVE_MULTI
                                healed = self._try_heal(tool, target, reason, handler, call, ctx)
                                if healed is not None:
                                    results.append(healed)
                                    self._emit_report(ctx, idx, tool, healed, extra=getattr(self, "_last_heal_extra", None))
                                    self._emit_metric(tool, healed)
                                    continue
                                res = StepResult(ok=False, reason=reason)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = candidates[0]
                        else:
                            resolved_candidate, timed_out = self._poll_resolve(finder, target, timeout_ms)
                            if resolved_candidate is None:
                                healed = self._try_heal(tool, target, R.TIMEOUT_RESOLVE, handler, call, ctx)
                                if healed is not None:
                                    results.append(healed)
                                    self._emit_report(ctx, idx, tool, healed, extra=getattr(self, "_last_heal_extra", None))
                                    self._emit_metric(tool, healed)
                                    continue
                                res = StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = resolved_candidate
                    else:
                        # No live snapshot available for resolve(); require a finder
                        healed = self._try_heal(tool, target, R.RESOLVER_NO_FIND, handler, call, ctx)
                        if healed is not None:
                            results.append(healed)
                            self._emit_report(ctx, idx, tool, healed, extra=getattr(self, "_last_heal_extra", None))
                            self._emit_metric(tool, healed)
                            continue
                        res = StepResult(ok=False, reason=R.RESOLVER_NO_FIND)
                        results.append(res)
                        self._emit_report(ctx, idx, tool, res)
                        self._emit_metric(tool, res)
                        continue

                # Attach resolved info for handlers via meta (non-schema execution detail)
                if resolved is not None:
                    meta = dict(call.get("meta") or {})
                    meta["resolved"] = resolved
                    call["meta"] = meta

                # Click safety policy
                if tool == "click":
                    safety_reason = self._check_click_safety(resolved)
                    if safety_reason is not None:
                        healed = self._try_heal(tool, target or {}, safety_reason, handler, call, ctx)
                        if healed is not None:
                            results.append(healed)
                            self._emit_report(ctx, idx, tool, healed, extra=getattr(self, "_last_heal_extra", None))
                            self._emit_metric(tool, healed)
                            continue
                        res = StepResult(ok=False, reason=safety_reason, signature=self._build_signature(resolved))
                        results.append(res)
                        self._emit_report(ctx, idx, tool, res, duration=(time.time() - step_start))
                        self._emit_metric(tool, res)
                        continue

                res = handler.execute(call, ctx)
                # attach signature when we have a resolved candidate
                if resolved is not None and isinstance(res, StepResult) and res.signature is None:
                    res.signature = self._build_signature(resolved)
                results.append(res)
                self._emit_report(ctx, idx, tool, res, duration=(time.time() - step_start))
                self._emit_metric(tool, res)
                continue

            # Unsupported tools for now
            res = StepResult(ok=False, reason=R.UNSUPPORTED_TOOL)
            results.append(res)
            self._emit_report(ctx, idx, tool or "<none>", res, duration=(time.time() - step_start))
            self._emit_metric(tool or "<none>", res)
        return results

    def get_last_heal_stats(self) -> dict:
        # Determine final healer mode used with precedence: llm > deterministic > none
        mode = "llm" if getattr(self, "_llm_attempted", False) else (
            "deterministic" if getattr(self, "_det_attempted", False) else "none"
        )
        attempts = int(getattr(self, "_heal_attempts", 0) or 0)
        successes = int(getattr(self, "_heal_successes", 0) or 0)
        rate = successes / attempts if attempts else 0.0
        return {"healer": mode, "heal_attempts": attempts, "heal_successes": successes, "healed_rate": rate}

    def _now_ms(self) -> int:
        if self._clock is not None:
            n = self._clock.now()
            if isinstance(n, datetime):
                return int(n.timestamp() * 1000)
        return int(time.time() * 1000)

    def _poll_resolve(self, finder: Callable[[dict], Any], target: dict, timeout_ms: int) -> tuple[Any | None, bool]:
        start = self._now_ms()
        attempts = 0
        while True:
            try:
                candidates = finder(target) or []
            except Exception:
                candidates = []
            if len(candidates) == 1:
                return candidates[0], False
            attempts += 1
            if attempts >= self._max_attempts:
                return None, True
            if (self._now_ms() - start) > timeout_ms:
                return None, True

    def _check_click_safety(self, candidate: Any) -> str | None:
        # Fail-closed default: missing flags are treated as False
        visible = False
        enabled = False
        if isinstance(candidate, dict):
            try:
                visible = bool(candidate.get("visible", False))
                enabled = bool(candidate.get("enabled", False))
            except Exception:
                visible = False
                enabled = False
        if not visible:
            return R.NOT_VISIBLE
        if not enabled:
            return R.NOT_ENABLED
        return None

    def _build_signature(self, candidate: Any) -> dict:
        if not isinstance(candidate, dict):
            return {}
        sig: dict = {}
        # direct fields
        for key in ("id", "classes", "role", "name", "visible", "enabled"):
            if key in candidate:
                sig[key] = candidate.get(key)
        # normalized testid from attrs/testid/data-testid
        attrs = candidate.get("attrs") or {}
        if isinstance(attrs, dict):
            testid = attrs.get("data-testid") or attrs.get("testid")
            if testid:
                sig["testid"] = testid
        # locator basics if present
        for key in ("type", "value"):
            if key in candidate:
                sig[key] = candidate.get(key)
        # neighborText if provided by resolver/caller
        if "neighborText" in candidate:
            sig["neighborText"] = candidate.get("neighborText")
        return sig

    def _emit_report(self, ctx: ExecCtx, index: int, tool: str, res: StepResult, duration: float | None = None, extra: dict | None = None) -> None:
        if not self._reporter:
            return
        payload = {
            "run_id": ctx.run_id,
            "index": index,
            "tool": tool,
            "ok": res.ok,
            "reason": res.reason,
        }
        if duration is not None:
            try:
                payload["duration"] = float(duration)
            except Exception:
                pass
        # Optional per-step enrichment (healing flags)
        if self._settings and getattr(self._settings, "REPORT_STEP_HEAL_FLAGS", False) and extra:
            payload.update(extra)
        self._reporter.on_step(payload)

    def _emit_metric(self, tool: str, res: StepResult) -> None:
        if not self._reporter:
            return
        metric = getattr(self._reporter, "on_metric", None) or getattr(
            self._reporter, "increment", None
        )
        if callable(metric):
            try:
                metric(
                    "executor_step_total",
                    tags={
                        "tool": tool,
                        "ok": bool(res.ok),
                        "reason": res.reason or "none",
                    },
                )
            except TypeError:
                # best-effort in case reporter signature differs
                metric("executor_step_total")

    def _try_heal(
        self,
        tool: str,
        target: dict,
        failure_reason: str,
        handler: IActionHandler,
        call: dict,
        ctx: ExecCtx,
    ) -> StepResult | None:
        if not self._settings or not getattr(self._settings, "HEALER_ENABLED", False):
            return None
        # Choose path
        path = getattr(self._settings, "HEALER_PATH", "deterministic")
        healed = None
        # OTel Phase 1: trace heal attempts
        _span_ctx = None
        try:
            from opentelemetry import trace as _trace

            tracer = _trace.get_tracer("kaizen.engine.heal")
            _span_ctx = tracer.start_as_current_span("heal.attempt")
            _span_cm = _span_ctx.__enter__()
            try:
                _span_cm.set_attribute("tool", tool)
                _span_cm.set_attribute("reason", failure_reason)
            except Exception:
                pass
        except Exception:
            _span_ctx = None
        if path == "llm" and self._llm is not None:
            # Attempt LLM first
            self._heal_attempts += 1
            self._llm_attempted = True
            healed = self._llm_propose(target, failure_reason)
            if healed is None and self._healer is not None:
                # fallback to deterministic heuristics
                self._heal_attempts += 1
                self._det_attempted = True
                healed = self._healer.heal({"reason": failure_reason, "target": target}, {"tool": tool, "run_id": ctx.run_id})
        else:
            if self._healer is None:
                # close span if opened
                try:
                    if _span_ctx is not None:
                        _span_cm = getattr(_span_ctx, "__exit__", None)
                        if callable(_span_cm):
                            _span_ctx.__exit__(None, None, None)
                except Exception:
                    pass
                return None
            self._heal_attempts += 1
            self._det_attempted = True
            healed = self._healer.heal({"reason": failure_reason, "target": target}, {"tool": tool, "run_id": ctx.run_id})

        # close span with outcome
        try:
            if _span_ctx is not None:
                ok = bool(healed and isinstance(healed, dict) and isinstance(healed.get("primary"), dict))
                _span_cm = getattr(_span_ctx, "__enter__", None)
                # _span_ctx is an active context manager; get current span to set attrs
                from opentelemetry import trace as _trace

                span = _trace.get_current_span()
                try:
                    span.set_attribute("strategy", "llm" if getattr(self, "_llm_attempted", False) else ("deterministic" if getattr(self, "_det_attempted", False) else "none"))
                    span.set_attribute("success", ok)
                except Exception:
                    pass
                _span_ctx.__exit__(None, None, None)
        except Exception:
            pass
        if not healed or not isinstance(healed, dict):
            return None
        primary = healed.get("primary")
        if not isinstance(primary, dict):
            return None
        meta = dict(call.get("meta") or {})
        meta["resolved"] = primary
        call["meta"] = meta
        if tool == "click":
            safety_reason = self._check_click_safety(primary)
            if safety_reason is not None:
                return StepResult(ok=False, reason=safety_reason, signature=self._build_signature(primary))
        res = handler.execute(call, ctx)
        if isinstance(res, StepResult) and res.signature is None:
            res.signature = self._build_signature(primary)
        if isinstance(res, StepResult) and res.ok:
            self._heal_successes += 1
            # capture per-step enrichment
            self._last_heal_extra = {
                "healed": True,
                "healer": ("llm" if self._llm_attempted else ("deterministic" if self._det_attempted else "none")),
                "confidence": float(healed.get("confidence", 0.0)) if isinstance(healed, dict) else 0.0,
            }
        return res

    def _llm_propose(self, target: dict, reason: str) -> dict | None:
        try:
            import json

            prompt = (
                "Propose CSS selector candidates as JSON for the target. "
                "Respond as {\"primary\":{\"type\":\"css\",\"value\": "
                "string}, \"fallbacks\":[...], \"confidence\": 0..1}."
            )
            ctx = {"reason": reason, "target": target}
            raw = self._llm.ask(json.dumps(ctx))
            data = json.loads(raw)
            # Normalize minimal forms
            if isinstance(data, dict) and "primary" not in data and "type" in data and "value" in data:
                data = {"primary": data, "fallbacks": [], "confidence": 0.5}
            if not isinstance(data, dict):
                return None
            primary = data.get("primary")
            if not isinstance(primary, dict):
                return None
            # Ensure minimal locator fields
            if primary.get("type") != "css" or not isinstance(primary.get("value"), str):
                return None
            # Mark safe flags if absent
            primary.setdefault("visible", True)
            primary.setdefault("enabled", True)
            fallbacks = data.get("fallbacks") if isinstance(data.get("fallbacks"), list) else []
            norm_fallbacks = []
            for f in fallbacks:
                if isinstance(f, dict) and f.get("type") == "css" and isinstance(f.get("value"), str):
                    f.setdefault("visible", True)
                    f.setdefault("enabled", True)
                    norm_fallbacks.append(f)
            conf = data.get("confidence")
            try:
                conf = float(conf)
            except Exception:
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            return {"primary": primary, "fallbacks": norm_fallbacks, "confidence": conf}
        except Exception:
            return None

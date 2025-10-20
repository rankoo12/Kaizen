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
    ):
        self._browser = browser
        self._handlers = handlers or {}
        self._resolver = resolver
        self._log = log
        self._reporter = reporter
        self._clock = clock
        self._settings = settings
        self._max_attempts = 50

    def execute(self, plan: Plan, *, ctx: ExecCtx) -> List[StepResult]:
        results: List[StepResult] = []
        for idx, call in enumerate(plan):
            tool = call.get("tool")
            args: dict[str, Any] = call.get("args", {})

            # Safety checks beyond schema
            if not tool or not isinstance(args, dict):
                res = StepResult(ok=False, reason=R.INVALID_TOOLCALL)
                results.append(res)
                self._emit_metric(tool or "<none>", res)
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
                    schemes = (self._settings.ALLOWED_URL_SCHEMES if self._settings else ["data:", "about:blank"]) or []
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
                    self._emit_report(ctx, idx, tool, res)
                    self._emit_metric(tool, res)
                    continue

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(ctx, idx, tool, res)
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
                            # Legacy immediate behavior
                            try:
                                candidates = finder(target) or []
                            except Exception:
                                candidates = []
                            if len(candidates) != 1:
                                reason = R.RESOLVE_ZERO if len(candidates) == 0 else R.RESOLVE_MULTI
                                res = StepResult(ok=False, reason=reason)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = candidates[0]
                        else:
                            resolved_candidate, timed_out = self._poll_resolve(finder, target, timeout_ms)
                            if resolved_candidate is None:
                                res = StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = resolved_candidate
                    else:
                        # No live snapshot available for resolve(); require a finder
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
                        res = StepResult(ok=False, reason=safety_reason)
                        results.append(res)
                        self._emit_report(ctx, idx, tool, res)
                        self._emit_metric(tool, res)
                        continue

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(ctx, idx, tool, res)
                self._emit_metric(tool, res)
                continue

            # Unsupported tools for now
            res = StepResult(ok=False, reason=R.UNSUPPORTED_TOOL)
            results.append(res)
            self._emit_report(ctx, idx, tool or "<none>", res)
            self._emit_metric(tool or "<none>", res)
        return results

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
            if (self._now_ms() - start) >= timeout_ms:
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

    def _emit_report(self, ctx: ExecCtx, index: int, tool: str, res: StepResult) -> None:
        if not self._reporter:
            return
        self._reporter.on_step(
            {
                "run_id": ctx.run_id,
                "index": index,
                "tool": tool,
                "ok": res.ok,
                "reason": res.reason,
            }
        )

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

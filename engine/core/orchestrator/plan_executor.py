from __future__ import annotations

from typing import List, Any, Callable

from engine.core.orchestrator.types import IPlanExecutor, Plan
from engine.core.commands.action_handler import StepResult, ExecCtx, IActionHandler
from engine.core.logging.log import ILog
from engine.core.browser.browser_port import IBrowser
from engine.core.resolving.element_resolver import IElementResolver
from engine.core.reporting.reporter import IReporter
from engine.core.time.clock import IClock


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
    ):
        self._browser = browser
        self._handlers = handlers or {}
        self._resolver = resolver
        self._log = log
        self._reporter = reporter
        self._clock = clock

    def execute(self, plan: Plan, *, ctx: ExecCtx) -> List[StepResult]:
        results: List[StepResult] = []
        for idx, call in enumerate(plan):
            tool = call.get("tool")
            args: dict[str, Any] = call.get("args", {})

            # Safety checks beyond schema
            if not tool or not isinstance(args, dict):
                results.append(StepResult(ok=False, reason="invalid_toolcall"))
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
                results.append(StepResult(ok=False, reason="missing_handler"))
                continue

            # Enforce offline-safe open policy
            if tool == "open":
                url = args.get("url", "")
                if not (isinstance(url, str) and (url.startswith("data:") or url == "about:blank")):
                    results.append(StepResult(ok=False, reason="url_not_allowed"))
                    continue

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(ctx, idx, tool, res)
                continue

            # Resolve target deterministically for interactive actions
            if tool in {"click", "type", "press"}:
                target = args.get("target")
                # press may not require a target
                requires_target = tool in {"click", "type"}
                if requires_target and not isinstance(target, dict):
                    results.append(StepResult(ok=False, reason="missing_target"))
                    continue

                resolved = None
                if isinstance(target, dict) and self._resolver is not None:
                    # Prefer a 'find' method if available (duck-typing), else fallback
                    finder: Callable[[dict], Any] | None = getattr(self._resolver, "find", None)
                    if callable(finder):
                        try:
                            candidates = finder(target) or []
                        except Exception:
                            candidates = []
                        if len(candidates) != 1:
                            reason = (
                                "resolve_zero_candidates" if len(candidates) == 0 else "resolve_multiple_candidates"
                            )
                            results.append(StepResult(ok=False, reason=reason))
                            continue
                        resolved = candidates[0]
                    else:
                        # No live snapshot available for resolve(); require a finder
                        results.append(StepResult(ok=False, reason="resolver_no_find"))
                        continue

                # Attach resolved info for handlers via meta (non-schema execution detail)
                if resolved is not None:
                    meta = dict(call.get("meta") or {})
                    meta["resolved"] = resolved
                    call["meta"] = meta

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(ctx, idx, tool, res)
                continue

            # Unsupported tools for now
            results.append(StepResult(ok=False, reason="unsupported_tool"))
        return results

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

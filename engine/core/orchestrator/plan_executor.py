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
from engine.core.config.settings import Settings, settings as _settings
from engine.core.healing.selector_healer import ISelectorHealer
from engine.core.llm.text_llm import ILLMText
from engine.core.perception import IPerceptionLayer


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
        storage: Any | None = None,
        llm: ILLMText | None = None,
        perception_layer: IPerceptionLayer | None = None,
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
        self._storage = storage
        self._current_domain: str | None = None
        self._profile_hits = 0
        self._profile_misses = 0
        self._run_tenant_id: str | None = None
        self._perception = perception_layer

    def execute(self, plan: Plan, *, ctx: ExecCtx) -> List[StepResult]:
        # reset heal stats per execution
        self._heal_attempts = 0
        self._heal_successes = 0
        self._healer_mode_used = "none"
        self._llm_attempted = False
        self._det_attempted = False
        # remember last successfully resolved clickable target to support
        # glue-flow typing into the previously clicked field
        self._last_target: Any | None = None
        self._profile_hits = 0
        self._profile_misses = 0
        self._last_heal_extra = None
        # Resolve tenant for this run once (used for PageBrain model selection)
        self._selector_feedback: dict[str, dict[str, int]] = {}
        try:
            if getattr(self, "_storage", None) is not None:
                get_run = getattr(self._storage, "get_run", None)
                feedback_fn = getattr(self._storage, "get_selector_feedback_for_test", None)
                if callable(get_run):
                    row = get_run(str(ctx.run_id))
                    if isinstance(row, dict):
                        if getattr(self, "_run_tenant_id", None) is None:
                            self._run_tenant_id = row.get("tenant_id")
                        test_id = row.get("test_id")
                        if test_id and callable(feedback_fn):
                            fb = feedback_fn(str(test_id))
                            if isinstance(fb, dict):
                                self._selector_feedback = fb
        except Exception:
            self._run_tenant_id = None
            self._selector_feedback = {}
        # Inform resolver of tenant when supported
        try:
            if self._resolver is not None:
                setter = getattr(self._resolver, "set_tenant", None)
                if callable(setter):
                    setter(self._run_tenant_id)
        except Exception:
            pass
        # Inform resolver of selector feedback (human labels) when supported
        try:
            if self._resolver is not None:
                fb_setter = getattr(self._resolver, "set_selector_feedback", None)
                if callable(fb_setter):
                    fb_setter(self._selector_feedback or {})
        except Exception:
            pass

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
                    self._emit_report(
                        ctx,
                        idx,
                        tool or "<none>",
                        res,
                        duration=(time.time() - step_start),
                    )
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
                    schemes = (
                        getattr(
                            self._settings,
                            "ALLOWED_URL_SCHEMES",
                            ["data:", "about:blank"],
                        )
                        or []
                    )
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
                    # Fail fast: abort further steps when navigation is blocked
                    res = StepResult(ok=False, reason=R.URL_SCHEME_NOT_ALLOWED)
                    results.append(res)
                    self._emit_report(
                        ctx, idx, tool, res, duration=(time.time() - step_start)
                    )
                    self._emit_metric(tool, res)
                    break

                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(
                    ctx, idx, tool, res, duration=(time.time() - step_start)
                )
                # Track current domain for subsequent profile save/lookup
                try:
                    if isinstance(url, str):
                        self._current_domain = self._extract_domain(url)
                except Exception:
                    self._current_domain = None
                self._emit_metric(tool, res)
                continue

            # Resolve target deterministically for interactive actions
            if tool in {"click", "type", "press", "waitFor", "doubleClick", "rightClick", "hover", "focus", "blur", "clear", "select", "upload", "drag", "dragAndDrop", "download"}:
                target = args.get("target")
                # press/assertUrl/custom may not require a target
                requires_target = (
                    tool in {"click", "type", "assertVisible", "assertText", "doubleClick", "rightClick", "hover", "focus", "blur", "clear", "select", "upload", "drag", "dragAndDrop"}
                    or (tool == "waitFor" and isinstance(args.get("target"), dict))
                )
                if requires_target and not isinstance(target, dict):
                    res = StepResult(ok=False, reason=R.MISSING_TARGET)
                    results.append(res)
                    self._emit_report(ctx, idx, tool, res)
                    self._emit_metric(tool, res)
                    continue

                resolved = None
                pagebrain_meta = None
                if isinstance(target, dict) and self._resolver is not None:
                    # Prefer a 'find' method if available (duck-typing), else fallback
                    finder: Callable[[dict], Any] | None = getattr(
                        self._resolver, "find", None
                    )
                    if callable(finder):
                        timeout_ms = ctx.timeout_ms
                        if timeout_ms is None:
                            timeout_ms = getattr(
                                self._settings, "EXEC_TIMEOUT_MS", None
                            )
                        if timeout_ms is None:
                            # Legacy immediate behavior
                            try:
                                candidates = finder(target) or []
                            except Exception:
                                candidates = []
                            if len(candidates) != 1:
                                reason = (
                                    R.RESOLVE_ZERO
                                    if len(candidates) == 0
                                    else R.RESOLVE_MULTI
                                )
                                healed = self._try_heal(
                                    tool, target, reason, handler, call, ctx
                                )
                                if healed is not None:
                                    results.append(healed)
                                    self._emit_report(
                                        ctx,
                                        idx,
                                        tool,
                                        healed,
                                        extra=getattr(self, "_last_heal_extra", None),
                                    )
                                    self._emit_metric(tool, healed)
                                    continue
                                res = StepResult(ok=False, reason=reason)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = candidates[0]
                            # Capture PageBrain metadata when provided by resolver
                            try:
                                pb_get = getattr(self._resolver, "get_last_pagebrain", None)
                                if callable(pb_get):
                                    pagebrain_meta = pb_get()
                            except Exception:
                                pagebrain_meta = None
                        else:
                            resolved_candidate, timed_out = self._poll_resolve(
                                finder, target, timeout_ms
                            )
                            if resolved_candidate is None:
                                healed = self._try_heal(
                                    tool, target, R.TIMEOUT_RESOLVE, handler, call, ctx
                                )
                                if healed is not None:
                                    results.append(healed)
                                    self._emit_report(
                                        ctx,
                                        idx,
                                        tool,
                                        healed,
                                        extra=getattr(self, "_last_heal_extra", None),
                                    )
                                    self._emit_metric(tool, healed)
                                    continue
                                res = StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
                                results.append(res)
                                self._emit_report(ctx, idx, tool, res)
                                self._emit_metric(tool, res)
                                continue
                            resolved = resolved_candidate
                            try:
                                pb_get = getattr(self._resolver, "get_last_pagebrain", None)
                                if callable(pb_get):
                                    pagebrain_meta = pb_get()
                            except Exception:
                                pagebrain_meta = None
                    else:
                        # No live snapshot available for resolve(); require a finder
                        healed = self._try_heal(
                            tool, target, R.RESOLVER_NO_FIND, handler, call, ctx
                        )
                        if healed is not None:
                            results.append(healed)
                            self._emit_report(
                                ctx,
                                idx,
                                tool,
                                healed,
                                extra=getattr(self, "_last_heal_extra", None),
                            )
                            self._emit_metric(tool, healed)
                            continue
                        res = StepResult(ok=False, reason=R.RESOLVER_NO_FIND)
                        results.append(res)
                        self._emit_report(ctx, idx, tool, res)
                        self._emit_metric(tool, res)
                        continue

                # If typing with a generic/ambiguous target, prefer last clicked element
                if tool == "type":
                    try:
                        t = target or {}
                        t_is_generic = False
                        if isinstance(t, dict):
                            # generic hints often used by glue path
                            if (t.get("text") == "input") or (t.get("css") == "input"):
                                t_is_generic = True
                        # If the previous step was a click and succeeded (we store _last_target only on success),
                        # prefer typing into that element regardless of the current target specificity.
                        try:
                            prev_was_click = False
                            if idx > 0:
                                prev = plan[idx - 1] if isinstance(plan, list) else None
                                prev_was_click = (
                                    isinstance(prev, dict)
                                    and prev.get("tool") == "click"
                                )
                        except Exception:
                            prev_was_click = False
                        if (
                            getattr(self, "_last_target", None) is not None
                            and prev_was_click
                        ):
                            resolved = self._last_target
                        elif (resolved is None or t_is_generic) and getattr(
                            self, "_last_target", None
                        ) is not None:
                            resolved = self._last_target
                    except Exception:
                        pass

                # Special case: dragAndDrop needs to resolve destination 'to' as well
                if tool == "dragAndDrop":
                    try:
                        to_target = args.get("to")
                        if not isinstance(to_target, dict):
                            res = StepResult(ok=False, reason=R.MISSING_TARGET)
                            results.append(res)
                            self._emit_report(ctx, idx, tool, res)
                            self._emit_metric(tool, res)
                            continue
                        # Resolve destination using same policy
                        finder: Callable[[dict], Any] | None = getattr(self._resolver, "find", None)
                        if callable(finder):
                            timeout_ms = ctx.timeout_ms or getattr(self._settings, "EXEC_TIMEOUT_MS", None)
                            if timeout_ms is None:
                                try:
                                    dests = finder(to_target) or []
                                except Exception:
                                    dests = []
                                if len(dests) != 1:
                                    res = StepResult(ok=False, reason=(R.RESOLVE_ZERO if len(dests) == 0 else R.RESOLVE_MULTI))
                                    results.append(res)
                                    self._emit_report(ctx, idx, tool, res)
                                    self._emit_metric(tool, res)
                                    continue
                                dest_resolved = dests[0]
                            else:
                                dest_resolved, _ = self._poll_resolve(finder, to_target, timeout_ms)
                                if dest_resolved is None:
                                    res = StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
                                    results.append(res)
                                    self._emit_report(ctx, idx, tool, res)
                                    self._emit_metric(tool, res)
                                    continue
                        else:
                            res = StepResult(ok=False, reason=R.RESOLVER_NO_FIND)
                            results.append(res)
                            self._emit_report(ctx, idx, tool, res)
                            self._emit_metric(tool, res)
                            continue
                    except Exception:
                        res = StepResult(ok=False, reason=R.TIMEOUT_RESOLVE)
                        results.append(res)
                        self._emit_report(ctx, idx, tool, res)
                        self._emit_metric(tool, res)
                        continue
                else:
                    dest_resolved = None

                # Attach resolved info for handlers via meta (non-schema execution detail)
                if resolved is not None:
                    meta = dict(call.get("meta") or {})
                    meta["resolved"] = resolved
                    if tool == "dragAndDrop" and dest_resolved is not None:
                        meta["resolved_to"] = dest_resolved
                    if pagebrain_meta:
                        meta["pagebrain"] = pagebrain_meta
                    call["meta"] = meta

                # Click safety policy
                if tool in {"click", "doubleClick", "rightClick"}:
                      safety_reason = self._check_click_safety(resolved)
                      if safety_reason is not None:
                          healed = self._try_heal(
                              tool, target or {}, safety_reason, handler, call, ctx
                          )
                          if healed is not None:
                              results.append(healed)
                              self._emit_report(
                                  ctx,
                                  idx,
                                  tool,
                                  healed,
                                  extra=getattr(self, "_last_heal_extra", None),
                              )
                              self._emit_metric(tool, healed)
                              continue
                          res = StepResult(
                              ok=False,
                              reason=safety_reason,
                              signature=self._build_signature(resolved),
                          )
                          results.append(res)
                          self._emit_report(
                              ctx, idx, tool, res, duration=(time.time() - step_start)
                          )
                          self._emit_metric(tool, res)
                          continue

                # reset per-action heal metadata
                self._last_heal_extra = None
                action_artifacts: dict[str, str] = {}
                # Best-effort per-action screenshots for ML/portal review
                try:
                    before_name = self._capture_step_screenshot(ctx, idx, phase="before")
                    if before_name:
                        action_artifacts["screenshot_before"] = before_name
                except Exception:
                    pass
                res = handler.execute(call, ctx)
                try:
                    after_name = self._capture_step_screenshot(ctx, idx, phase="after")
                    if after_name:
                        action_artifacts["screenshot_after"] = after_name
                except Exception:
                    pass
                # Optional PerceptionLayer: compute deterministic 3-layer diff
                perception_block = None
                try:
                    if self._perception is not None:
                        from pathlib import Path

                        logs_dir = getattr(_settings, "LOGS_DIR", Path("logs"))
                        logs_dir.mkdir(parents=True, exist_ok=True)
                        run_id = getattr(ctx, "run_id", None) or "run"
                        before_path = logs_dir / f"screenshot-{run_id}-a{idx}-before.png"
                        after_path = logs_dir / f"screenshot-{run_id}-a{idx}-after.png"
                        bbox = None
                        try:
                            if isinstance(resolved, dict):
                                bbox = resolved.get("bbox")
                        except Exception:
                            bbox = None
                        perception_block = self._perception.compute(
                            tool=tool,
                            before_path=str(before_path) if before_path.exists() else None,
                            after_path=str(after_path) if after_path.exists() else None,
                            bbox=bbox if isinstance(bbox, dict) else None,
                            dom_snapshot_id=None,
                        )
                except Exception:
                    perception_block = None
                # Emit PageBrain choice event for logging/datasets when available
                try:
                    if self._log and pagebrain_meta:
                        self._log.info(
                            "pagebrain.choice",
                            run_id=getattr(ctx, "run_id", None),
                            tool=tool,
                            ok=bool(getattr(res, "ok", False)),
                            reason=getattr(res, "reason", None),
                            target_signature=getattr(res, "signature", None),
                            pagebrain=pagebrain_meta,
                        )
                except Exception:
                    pass
                # Attach signature based on the actual selector used. Handlers may
                # update call["meta"]["resolved"] when they apply fallbacks.
                actual_resolved = None
                try:
                    actual_resolved = (call.get("meta") or {}).get(
                        "resolved"
                    ) or resolved
                except Exception:
                    actual_resolved = resolved
                if (
                    actual_resolved is not None
                    and isinstance(res, StepResult)
                    and res.signature is None
                ):
                    res.signature = self._build_signature(actual_resolved)
                # Emit ActionRun log for datasets (PageBrain + Healer summary)
                try:
                    if self._log:
                        selector = None
                        if isinstance(actual_resolved, dict):
                            selector = {
                                "type": actual_resolved.get("type"),
                                "value": actual_resolved.get("value"),
                                "visible": actual_resolved.get("visible"),
                                "enabled": actual_resolved.get("enabled"),
                            }
                        executor_block = {
                            "status": "passed" if getattr(res, "ok", False) else "failed",
                            "reason": getattr(res, "reason", None),
                            "selector": selector,
                            "signature": getattr(res, "signature", None),
                        }
                        self._log.info(
                            "action.run",
                            run_id=getattr(ctx, "run_id", None),
                            index=idx,
                            action_index=idx,
                            tool=tool,
                            ok=bool(getattr(res, "ok", False)),
                            reason=getattr(res, "reason", None),
                            semantic_target=target,
                            target_signature=getattr(res, "signature", None),
                            executor=executor_block,
                            pagebrain=pagebrain_meta,
                            healer=getattr(self, "_last_heal_extra", None),
                            perception=perception_block,
                            artifacts=action_artifacts or None,
                        )
                except Exception:
                    pass
                # If a click failed, attempt healer recovery as a secondary path
                if tool in {"click", "doubleClick", "rightClick"} and isinstance(res, StepResult) and not res.ok:
                    try:
                        failure_reason = getattr(res, "reason", None) or R.CLICK_TIMEOUT
                    except Exception:
                        failure_reason = R.CLICK_TIMEOUT
                    healed = self._try_heal(
                        tool, target or {}, failure_reason, handler, call, ctx
                    )
                    if healed is not None:
                        results.append(healed)
                        self._emit_report(
                            ctx,
                            idx,
                            tool,
                            healed,
                            duration=(time.time() - step_start),
                            extra=getattr(self, "_last_heal_extra", None),
                        )
                        self._emit_metric(tool, healed)
                        continue
                results.append(res)
                self._emit_report(
                    ctx, idx, tool, res, duration=(time.time() - step_start)
                )
                try:
                    if (
                        isinstance(res, StepResult)
                        and res.ok
                        and actual_resolved is not None
                    ):
                        self._maybe_save_profile(tool, res, actual_resolved)
                        self._maybe_save_embedding(tool, res, actual_resolved, ctx)
                        if tool in {"click", "doubleClick", "rightClick"}:
                            # remember last successful click target for subsequent type steps
                            self._last_target = actual_resolved
                except Exception:
                    pass
                self._emit_metric(tool, res)
                continue

            # Simple tools that don't require resolution (navigation, scroll)
            if tool in {"waitFor", "scroll", "reload", "back", "forward", "newTab", "newWindow", "switchTab", "switchWindow", "closeTab", "closeWindow", "download"}:
                res = handler.execute(call, ctx)
                results.append(res)
                self._emit_report(
                    ctx, idx, tool, res, duration=(time.time() - step_start)
                )
                self._emit_metric(tool, res)
                continue

            # Unsupported tools for now
            res = StepResult(ok=False, reason=R.UNSUPPORTED_TOOL)
            results.append(res)
            self._emit_report(
                ctx, idx, tool or "<none>", res, duration=(time.time() - step_start)
            )
            self._emit_metric(tool or "<none>", res)
        # Best-effort final screenshot for portal/runner artifacts
        try:
            if self._browser is not None:
                from pathlib import Path

                logs_dir = getattr(_settings, "LOGS_DIR", Path("logs"))
                logs_dir.mkdir(parents=True, exist_ok=True)
                out = logs_dir / f"screenshot-{getattr(ctx, 'run_id', 'run')}.png"
                # run browser.screenshot in place (handlers already use run_coro when available)
                take = getattr(self._browser, "screenshot", None)
                if callable(take):
                    try:
                        # try sync helper first if present
                        rc = getattr(self._browser, "run_coro", None)
                        if callable(rc):
                            rc(self._browser.screenshot(str(out)))
                        else:
                            # not ideal, but for local adapters fall back to async run
                            import asyncio

                            asyncio.run(self._browser.screenshot(str(out)))
                    except Exception:
                        pass
        except Exception:
            pass
        return results

    def _capture_step_screenshot(self, ctx: ExecCtx, action_index: int, phase: str = "before") -> str | None:
        """Capture a per-action screenshot for artifacts and portal review.

        Returns the artifact name (e.g. "screenshot/a0_before") when successful,
        or None when screenshots are unavailable or fail.
        """
        if self._browser is None:
            return None
        try:
            from pathlib import Path

            logs_dir = getattr(_settings, "LOGS_DIR", Path("logs"))
            logs_dir.mkdir(parents=True, exist_ok=True)
            run_id = getattr(ctx, "run_id", None) or "run"
            phase_norm = "after" if str(phase).lower() == "after" else "before"
            filename = f"screenshot-{run_id}-a{action_index}-{phase_norm}.png"
            out = logs_dir / filename
            take = getattr(self._browser, "screenshot", None)
            if not callable(take):
                return None
            try:
                run_coro = getattr(self._browser, "run_coro", None)
                if callable(run_coro):
                    run_coro(self._browser.screenshot(str(out)))
                else:
                    import asyncio

                    asyncio.run(self._browser.screenshot(str(out)))
            except Exception:
                return None
            return f"screenshot/a{action_index}_{phase_norm}"
        except Exception:
            return None

    def get_last_heal_stats(self) -> dict:
        # Determine final healer mode used with precedence: llm > deterministic > none
        mode = (
            "llm"
            if getattr(self, "_llm_attempted", False)
            else ("deterministic" if getattr(self, "_det_attempted", False) else "none")
        )
        attempts = int(getattr(self, "_heal_attempts", 0) or 0)
        successes = int(getattr(self, "_heal_successes", 0) or 0)
        rate = successes / attempts if attempts else 0.0
        return {
            "healer": mode,
            "heal_attempts": attempts,
            "heal_successes": successes,
            "healed_rate": rate,
            "profile_hits": int(getattr(self, "_profile_hits", 0) or 0),
            "profile_misses": int(getattr(self, "_profile_misses", 0) or 0),
        }

    def _now_ms(self) -> int:
        if self._clock is not None:
            n = self._clock.now()
            if isinstance(n, datetime):
                return int(n.timestamp() * 1000)
        return int(time.time() * 1000)

    def _poll_resolve(
        self, finder: Callable[[dict], Any], target: dict, timeout_ms: int
    ) -> tuple[Any | None, bool]:
        start = self._now_ms()
        attempts = 0
        while True:
            try:
                candidates = finder(target) or []
            except Exception:
                candidates = []
            # Treat any non-empty candidate list as a successful resolve and
            # pick the first item as the primary target. Callers that care
            # about the full candidate set (e.g., PageBrain logging) already
            # receive it directly from resolver.find() outside this loop.
            if candidates:
                return candidates[0], False
            attempts += 1
            if attempts >= self._max_attempts:
                return None, True
            if (self._now_ms() - start) > timeout_ms:
                return None, True
            # brief backoff to avoid busy-spinning the CPU
            try:
                time.sleep(0.05)
            except Exception:
                pass

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

    def _emit_report(
        self,
        ctx: ExecCtx,
        index: int,
        tool: str,
        res: StepResult,
        duration: float | None = None,
        extra: dict | None = None,
    ) -> None:
        if not self._reporter:
            return
        payload = {
            "run_id": ctx.run_id,
            "index": index,
            "tool": tool,
            "ok": res.ok,
            "reason": res.reason,
        }
        # attach tenant when resolvable (for per-tenant metrics labeling downstream)
        try:
            if self._run_tenant_id is None and getattr(self, "_storage", None) is not None:
                get_run = getattr(self._storage, "get_run", None)
                if callable(get_run):
                    row = get_run(str(ctx.run_id))
                    if isinstance(row, dict):
                        self._run_tenant_id = row.get("tenant_id")
            if self._run_tenant_id is not None:
                payload["tenant_id"] = self._run_tenant_id
        except Exception:
            pass
        if duration is not None:
            try:
                payload["duration"] = float(duration)
            except Exception:
                pass
        # Optional per-step enrichment (healing flags)
        if (
            self._settings
            and getattr(self._settings, "REPORT_STEP_HEAL_FLAGS", False)
            and extra
        ):
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

    def _increment(self, name: str, tags: dict | None = None) -> None:
        if not self._reporter:
            return
        inc = getattr(self._reporter, "increment", None) or getattr(
            self._reporter, "on_metric", None
        )
        if callable(inc):
            try:
                inc(name, tags or {})
            except Exception:
                pass

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
        # PageBrain candidate fallback before healer strategies
        pb_candidates = []
        try:
            pb_meta = (call.get("meta") or {}).get("pagebrain") or {}
            pb_candidates = pb_meta.get("candidates") or []
        except Exception:
            pb_candidates = []
        for cand in pb_candidates:
            sel = cand.get("selector") if isinstance(cand, dict) else None
            if not isinstance(sel, dict):
                continue
            meta = dict(call.get("meta") or {})
            meta["resolved"] = sel
            call["meta"] = meta
            res = handler.execute(call, ctx)
            if isinstance(res, StepResult) and res.ok:
                res.signature = res.signature or self._build_signature(sel)
                self._last_heal_extra = {"healed": True, "healer": "pagebrain_candidate"}
                return res
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
            self._increment("healer_attempts_total", {"strategy": "llm", "tool": tool})
            healed = self._llm_propose(target, failure_reason)
            if healed is None and self._healer is not None:
                # fallback to deterministic heuristics
                self._heal_attempts += 1
                self._det_attempted = True
                self._increment(
                    "healer_attempts_total", {"strategy": "deterministic", "tool": tool}
                )
                healed = self._healer.heal(
                    {"reason": failure_reason, "target": target},
                    {
                        "tool": tool,
                        "run_id": ctx.run_id,
                        "domain": getattr(self, "_current_domain", None),
                    },
                )
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
            self._increment(
                "healer_attempts_total", {"strategy": "deterministic", "tool": tool}
            )
            healed = self._healer.heal(
                {"reason": failure_reason, "target": target},
                {
                    "tool": tool,
                    "run_id": ctx.run_id,
                    "domain": getattr(self, "_current_domain", None),
                },
            )

        # close span with outcome
        try:
            if _span_ctx is not None:
                ok = bool(
                    healed
                    and isinstance(healed, dict)
                    and isinstance(healed.get("primary"), dict)
                )
                _span_cm = getattr(_span_ctx, "__enter__", None)
                # _span_ctx is an active context manager; get current span to set attrs
                from opentelemetry import trace as _trace

                span = _trace.get_current_span()
                try:
                    span.set_attribute(
                        "strategy",
                        (
                            "llm"
                            if getattr(self, "_llm_attempted", False)
                            else (
                                "deterministic"
                                if getattr(self, "_det_attempted", False)
                                else "none"
                            )
                        ),
                    )
                    span.set_attribute("success", ok)
                except Exception:
                    pass
                _span_ctx.__exit__(None, None, None)
        except Exception:
            pass
        if not healed or not isinstance(healed, dict):
            # Count a profile miss when healing attempted without a profile hit
            try:
                if getattr(self, "_storage", None) is not None:
                    self._profile_misses += 1
            except Exception:
                pass
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
                return StepResult(
                    ok=False,
                    reason=safety_reason,
                    signature=self._build_signature(primary),
                )
        res = handler.execute(call, ctx)
        if isinstance(res, StepResult) and res.signature is None:
            res.signature = self._build_signature(primary)
        if isinstance(res, StepResult) and res.ok:
            self._heal_successes += 1
            self._increment("healer_successes_total", {"tool": tool})
            # capture per-step enrichment
            self._last_heal_extra = {
                "healed": True,
                "healer": (
                    "llm"
                    if self._llm_attempted
                    else ("deterministic" if self._det_attempted else "none")
                ),
                "confidence": (
                    float(healed.get("confidence", 0.0))
                    if isinstance(healed, dict)
                    else 0.0
                ),
            }
            try:
                self._maybe_save_profile(tool, res, primary)
                self._maybe_save_embedding(tool, res, primary, ctx)
            except Exception:
                pass
            # Ensure subsequent type uses the healed click target
            try:
                if tool == "click":
                    self._last_target = primary
            except Exception:
                pass
            # Profile KPIs: count hits when healer used a stored profile
            try:
                if isinstance(healed, dict) and healed.get("reason") == "profile_hit":
                    self._profile_hits += 1
                    self._increment("profile_hits_total", {"tool": tool})
                elif getattr(self, "_storage", None) is not None:
                    self._profile_misses += 1
                    self._increment("profile_misses_total", {"tool": tool})
            except Exception:
                pass
        return res

    def _maybe_save_profile(self, tool: str, res: StepResult, candidate: Any) -> None:
        if not getattr(self, "_storage", None):
            return
        if not isinstance(candidate, dict):
            return
        sel_type = candidate.get("type")
        sel_value = candidate.get("value")
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return
        selector = {"type": sel_type, "value": sel_value}
        target_signature = res.signature or {}
        save = getattr(self._storage, "save_locator_profile", None)
        if callable(save):
            save(
                domain=getattr(self, "_current_domain", None),
                tool=tool,
                target_signature=target_signature,
                selector=selector,
            )

    def _maybe_save_embedding(self, tool: str, res: StepResult, candidate: Any, ctx: ExecCtx) -> None:
        try:
            from engine.core.config.settings import settings as _settings

            if not getattr(_settings, "RETRIEVAL_SAVE_ON_SUCCESS", True):
                return
        except Exception:
            pass
        if not getattr(self, "_storage", None):
            return
        if not isinstance(candidate, dict):
            return
        if not isinstance(res, StepResult) or not res.ok:
            return
        sel_type = candidate.get("type")
        sel_value = candidate.get("value")
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return
        selector = {"type": sel_type, "value": sel_value}
        target_signature = res.signature or {}
        save = getattr(self._storage, "save_embedding_selector", None)
        if callable(save):
            tenant_id = None
            try:
                # Resolve tenant from run_id when available
                rid = getattr(ctx, "run_id", None)
                if rid and hasattr(self._storage, "get_run"):
                    row = self._storage.get_run(str(rid))
                    if isinstance(row, dict):
                        tenant_id = row.get("tenant_id")
            except Exception:
                tenant_id = None
            save(
                domain=getattr(self, "_current_domain", None),
                tool=tool,
                target_signature=target_signature,
                selector=selector,
                tenant_id=tenant_id,
            )

    def _llm_propose(self, target: dict, reason: str) -> dict | None:
        try:
            import json

            prompt = (
                "Propose CSS selector candidates as JSON for the target. "
                'Respond as {"primary":{"type":"css","value": '
                'string}, "fallbacks":[...], "confidence": 0..1}.'
            )
            ctx = {"reason": reason, "target": target}
            raw = self._llm.ask(json.dumps(ctx))
            data = json.loads(raw)
            # Normalize minimal forms
            if (
                isinstance(data, dict)
                and "primary" not in data
                and "type" in data
                and "value" in data
            ):
                data = {"primary": data, "fallbacks": [], "confidence": 0.5}
            if not isinstance(data, dict):
                return None
            primary = data.get("primary")
            if not isinstance(primary, dict):
                return None
            # Ensure minimal locator fields
            if primary.get("type") != "css" or not isinstance(
                primary.get("value"), str
            ):
                return None
            # Mark safe flags if absent
            primary.setdefault("visible", True)
            primary.setdefault("enabled", True)
            fallbacks = (
                data.get("fallbacks") if isinstance(data.get("fallbacks"), list) else []
            )
            norm_fallbacks = []
            for f in fallbacks:
                if (
                    isinstance(f, dict)
                    and f.get("type") == "css"
                    and isinstance(f.get("value"), str)
                ):
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

    def _extract_domain(self, url: str) -> str | None:
        try:
            from urllib.parse import urlparse
            from engine.core.net.domains import normalize_registrable_domain

            u = urlparse(url)
            host = u.hostname
            if not host:
                return None
            return normalize_registrable_domain(host)
        except Exception:
            return None

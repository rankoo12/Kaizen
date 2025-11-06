from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

import httpx

from engine.core.config.container import Container
from engine.core.reporting.reporter import IReporter, StepRun

# OpenTelemetry Phase 0 bootstrap (safe/no-op if deps missing)
_OTEL_ENABLED = False
_OTEL_TRACER = None
_OTEL_RUNS_COUNTER = None
_OTEL_RUN_HIST = None
_OTEL_STEP_HIST = None
_OTEL_RUNS_FAILED = None


def _init_otel(service_name: str = "kaizen-engine-runner") -> None:
    global _OTEL_ENABLED, _OTEL_TRACER, _OTEL_RUNS_COUNTER, _OTEL_RUN_HIST
    if _OTEL_ENABLED:
        return
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHTTPSpanExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter as OTLPHTTPMetricExporter,
        )
        import os
        # Instrument httpx for context propagation to Engine API
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except Exception:
            pass

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
        res = Resource.create({"service.name": service_name})

        # Traces
        tp = TracerProvider(resource=res)
        span_exporter = OTLPHTTPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        tp.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tp)
        _OTEL_TRACER = trace.get_tracer("kaizen.engine.runner")

        # Metrics
        metric_exporter = OTLPHTTPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
        reader = PeriodicExportingMetricReader(metric_exporter)
        mp = MeterProvider(resource=res, metric_readers=[reader])
        metrics.set_meter_provider(mp)
        meter = metrics.get_meter("kaizen.engine.runner")

        # instruments used in Phase 0
        _OTEL_RUNS_COUNTER = meter.create_counter(
            name="kaizen_runs_total",
            description="Total number of runs",
        )
        _OTEL_RUN_HIST = meter.create_histogram(
            name="kaizen_run_duration_seconds",
            unit="s",
            description="Duration of runs in seconds",
        )

        _OTEL_ENABLED = True
    except Exception:
        _OTEL_ENABLED = False
        _OTEL_TRACER = None
        _OTEL_RUNS_COUNTER = None
        _OTEL_RUN_HIST = None


class StatsCaptureReporter(IReporter):
    def __init__(self) -> None:
        self._last = None
        self._started: Dict[str, float] = {}
        self._modes: Dict[str, str] = {}
        self._on_start: Optional[callable] = None
        # OTel parent context for step spans (set by _run_job)
        self._otel_parent_ctx = None

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        self._started[str(run_id)] = time.time()
        self._modes[str(run_id)] = str(mode)
        if self._on_start:
            try:
                self._on_start(str(run_id))
            except Exception:
                pass
        # Annotate the active run span if present
        if _OTEL_ENABLED:
            try:
                from opentelemetry import trace as _trace

                span = _trace.get_current_span()
                try:
                    span.set_attribute("run_id", str(run_id))
                    span.set_attribute("mode", str(mode))
                except Exception:
                    pass
            except Exception:
                pass

    def on_step(self, step_run: StepRun) -> None:
        # Emit a child step span under the current run span + record metrics
        if not _OTEL_ENABLED:
            return
        try:
            from opentelemetry import trace as _trace, metrics as _metrics

            tracer = _OTEL_TRACER or _trace.get_tracer("kaizen.engine.runner.steps")
            meter = _metrics.get_meter("kaizen.engine.runner")
            global _OTEL_STEP_HIST
            if _OTEL_STEP_HIST is None:
                try:
                    _OTEL_STEP_HIST = meter.create_histogram(
                        name="kaizen_step_duration_seconds",
                        unit="s",
                        description="Duration per step",
                    )
                except Exception:
                    _OTEL_STEP_HIST = None

            tool = str(step_run.get("tool") or "<none>")
            name = f"step.{tool}"
            attrs = {
                "run_id": str(step_run.get("run_id")),
                "tool": tool,
                "reason": str(step_run.get("reason") or "none"),
            }
            for key in ("index", "ok", "healed", "healer"):
                if key in step_run:
                    attrs[key] = step_run.get(key)
            ctx = getattr(self, "_otel_parent_ctx", None)
            if ctx is not None:
                span_cm = tracer.start_as_current_span(name, context=ctx)
            else:
                span_cm = tracer.start_as_current_span(name)
            with span_cm as span:
                for k, v in attrs.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass
            # metric
            try:
                dur = step_run.get("duration")
                if _OTEL_STEP_HIST is not None and isinstance(dur, (int, float)):
                    _OTEL_STEP_HIST.record(float(dur), attributes={
                        "tool": tool,
                        "ok": bool(step_run.get("ok", False)),
                        "reason": str(step_run.get("reason") or "none"),
                    })
            except Exception:
                pass
        except Exception:
            # Guard: any instrumentation failure should not break runner
            pass

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self._last = {"run_id": run_id, "stats": dict(stats or {})}
        # Tag summary stats on the active span
        if _OTEL_ENABLED:
            try:
                from opentelemetry import trace as _trace
                from opentelemetry.trace import Status, StatusCode

                span = _trace.get_current_span()
                try:
                    span.set_attribute("stats.total", int((stats or {}).get("total", 0)))
                    span.set_attribute("stats.passed", int((stats or {}).get("passed", 0)))
                    span.set_attribute("stats.failed", int((stats or {}).get("failed", 0)))
                except Exception:
                    pass
                try:
                    if int((stats or {}).get("failed", 0) or 0) > 0:
                        span.set_status(Status(StatusCode.ERROR))
                except Exception:
                    pass
            except Exception:
                pass
        # Record failed runs counter
        if _OTEL_ENABLED:
            try:
                from opentelemetry import metrics as _metrics

                meter = _metrics.get_meter("kaizen.engine.runner")
                global _OTEL_RUNS_FAILED
                if _OTEL_RUNS_FAILED is None:
                    try:
                        _OTEL_RUNS_FAILED = meter.create_counter(
                            name="kaizen_runs_failed_total",
                            description="Total failed runs",
                        )
                    except Exception:
                        _OTEL_RUNS_FAILED = None
                failed = int((stats or {}).get("failed", 0) or 0)
                if _OTEL_RUNS_FAILED is not None and failed > 0:
                    mode = self._modes.get(str(run_id)) or "unknown"
                    _OTEL_RUNS_FAILED.add(1, attributes={"mode": mode})
            except Exception:
                pass

    def on_finish(self, run_id: str) -> None:
        pass

    def last(self):
        return self._last


async def _run_job(api_base: str, job: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create a top-level run span to cover the full job lifecycle
        _span_ctx = None
        _parent_ctx = None
        _extracted_parent = None
        if _OTEL_ENABLED:
            try:
                from opentelemetry import trace as _trace
                from opentelemetry.trace import set_span_in_context as _set_span_in_context
                from opentelemetry.propagate import extract as _extract

                tracer = _OTEL_TRACER or _trace.get_tracer("kaizen.engine.runner")
                # Try to extract parent context from job (traceparent/tracestate)
                try:
                    carrier = job.get("otel") or {}
                    if not carrier:
                        tp = job.get("traceparent")
                        ts = job.get("tracestate")
                        if tp or ts:
                            c = {}
                            if tp:
                                c["traceparent"] = tp
                            if ts:
                                c["tracestate"] = ts
                            carrier = c
                    if carrier:
                        _extracted_parent = _extract(carrier)
                except Exception:
                    _extracted_parent = None

                if _extracted_parent is not None:
                    _span_ctx = tracer.start_as_current_span("kaizen.run", context=_extracted_parent)
                else:
                    _span_ctx = tracer.start_as_current_span("kaizen.run")
                _span_ctx.__enter__()
                span = _trace.get_current_span()
                try:
                    span.set_attribute("job_id", str(job.get("job_id")))
                except Exception:
                    pass
                try:
                    _parent_ctx = _set_span_in_context(span)
                except Exception:
                    _parent_ctx = None
            except Exception:
                _span_ctx = None

        # mark job picked up
        try:
            await client.post(f"{api_base}/queue/running", json={"job_id": job.get("job_id")})
            print(f"[runner] picked job job_id={job.get('job_id')}")
        except Exception:
            pass

        # Build isolated container per job for safety
        container = Container()
        reporter = StatsCaptureReporter()
        try:
            reporter._otel_parent_ctx = _parent_ctx
        except Exception:
            pass

        # when on_run_start fires (live path), update running with run_id
        async def _on_start_async(run_id: str):
            try:
                await client.post(f"{api_base}/queue/running", json={"job_id": job.get("job_id"), "run_id": run_id})
            except Exception:
                pass

        # bridge sync reporter callback to async
        loop = asyncio.get_event_loop()

        def _on_start(run_id: str):
            loop.create_task(_on_start_async(run_id))
            try:
                print(f"[runner] on_run_start run_id={run_id}")
            except Exception:
                pass

        reporter._on_start = _on_start
        orchestrator = container.orchestrator(reporter=reporter)

        spec = job.get("spec") or {}
        mode = str(job.get("mode") or "snapshot").lower()

        run_id = None
        try:
            print(f"[runner] executing mode={mode} job_id={job.get('job_id')}")
            from time import time as _now
            start = _now()
            run_id = None
            if _OTEL_ENABLED:
                from opentelemetry import trace as _trace
                from opentelemetry.trace import Status, StatusCode

                span = _trace.get_current_span()
                try:
                    span.set_attribute("mode", mode)
                except Exception:
                    pass
                # Capture current context (with active run span) to propagate into worker thread
                _cv_ctx = None
                try:
                    import contextvars as _ctxv

                    _cv_ctx = _ctxv.copy_context()
                except Exception:
                    _cv_ctx = None
                if mode == "live":
                    if _cv_ctx is not None:
                        run_id = await asyncio.to_thread(
                            lambda: _cv_ctx.run(
                                orchestrator.run_live,
                                spec,
                                url=job.get("url"),
                            )
                        )
                    else:
                        run_id = await asyncio.to_thread(
                            orchestrator.run_live,
                            spec,
                            url=job.get("url"),
                        )
                else:
                    if _cv_ctx is not None:
                        run_id = await asyncio.to_thread(
                            lambda: _cv_ctx.run(
                                orchestrator.run_snapshot,
                                spec,
                                html_path=job.get("html_path"),
                                html=job.get("html"),
                                snapshot_path=job.get("snapshot") or job.get("snapshot_path"),
                            )
                        )
                    else:
                        run_id = await asyncio.to_thread(
                            orchestrator.run_snapshot,
                            spec,
                            html_path=job.get("html_path"),
                            html=job.get("html"),
                            snapshot_path=job.get("snapshot") or job.get("snapshot_path"),
                        )
                try:
                    span.set_attribute("run_id", str(run_id))
                except Exception:
                    pass
            else:
                if mode == "live":
                    run_id = await asyncio.to_thread(
                        orchestrator.run_live,
                        spec,
                        url=job.get("url"),
                    )
                else:
                    run_id = await asyncio.to_thread(
                        orchestrator.run_snapshot,
                        spec,
                        html_path=job.get("html_path"),
                        html=job.get("html"),
                        snapshot_path=job.get("snapshot") or job.get("snapshot_path"),
                    )
            dur = _now() - start
            try:
                if _OTEL_RUNS_COUNTER:
                    _OTEL_RUNS_COUNTER.add(1, attributes={"mode": mode})
                if _OTEL_RUN_HIST:
                    _OTEL_RUN_HIST.record(dur, attributes={"mode": mode})
            except Exception:
                pass
            # Post final stats
            last = reporter.last() or {"run_id": run_id, "stats": {}}
            payload = {"stats": last.get("stats", {})}
            try:
                await client.post(f"{api_base}/runs/{run_id}/finish", json=payload)
                print(f"[runner] posted finish run_id={run_id}")
            except Exception:
                pass
        except Exception as e:
            # Best-effort failure record
            try:
                if run_id is None:
                    run_id = f"job-{job.get('job_id')}-error"
                # Log the exception to help diagnose runner failures
                try:
                    import traceback as _tb

                    print("[runner] error:")
                    _tb.print_exc()
                except Exception:
                    print(f"[runner] error: {e!r}")
                await client.post(
                    f"{api_base}/runs/{run_id}/finish",
                    json={"stats": {"total": 0, "passed": 0, "failed": 1, "reasons": {"runner_error": 1}}},
                )
                print(f"[runner] posted failure run_id={run_id}")
            except Exception:
                pass
        finally:
            try:
                await client.post(f"{api_base}/queue/complete", json={"job_id": job.get("job_id"), "run_id": run_id})
                print(f"[runner] complete job_id={job.get('job_id')} run_id={run_id}")
            except Exception:
                pass
            # close the job-level span
            try:
                if _span_ctx is not None:
                    _span_ctx.__exit__(None, None, None)
            except Exception:
                pass


async def _poll_and_run(api_base: str, interval: float = 1.0) -> None:
    # Concurrency control via env
    try:
        max_conc = max(1, int(os.environ.get("RUNNER_CONCURRENCY", "1")))
    except Exception:
        max_conc = 1

    tasks: set[asyncio.Task] = set()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            # prune done tasks
            done = {t for t in tasks if t.done()}
            tasks -= done

            # fill available slots
            while len(tasks) < max_conc:
                try:
                    r = await client.get(f"{api_base}/queue/next")
                    r.raise_for_status()
                    job = r.json().get("job")
                except Exception:
                    job = None
                if not job:
                    print("[runner] queue empty")
                    break
                t = asyncio.create_task(_run_job(api_base, job))
                tasks.add(t)

            if len(tasks) >= max_conc:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(interval)


def main() -> None:
    api_base = os.environ.get("KAIZEN_API_BASE", "http://engine-api:8080/api")
    _init_otel("kaizen-engine-runner")
    asyncio.run(_poll_and_run(api_base))


if __name__ == "__main__":
    main()

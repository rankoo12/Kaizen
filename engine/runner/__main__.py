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
        self._on_start: Optional[callable] = None

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        self._started[str(run_id)] = time.time()
        if self._on_start:
            try:
                self._on_start(str(run_id))
            except Exception:
                pass

    def on_step(self, step_run: StepRun) -> None:
        pass

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self._last = {"run_id": run_id, "stats": dict(stats or {})}

    def on_finish(self, run_id: str) -> None:
        pass

    def last(self):
        return self._last


async def _run_job(api_base: str, job: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # mark job picked up
        try:
            await client.post(f"{api_base}/queue/running", json={"job_id": job.get("job_id")})
            print(f"[runner] picked job job_id={job.get('job_id')}")
        except Exception:
            pass

        # Build isolated container per job for safety
        container = Container()
        reporter = StatsCaptureReporter()

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

                tracer = _OTEL_TRACER or _trace.get_tracer("kaizen.engine.runner")
                with tracer.start_as_current_span("kaizen.run") as span:
                    try:
                        span.set_attribute("mode", mode)
                    except Exception:
                        pass
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
        except Exception:
            # Best-effort failure record
            try:
                if run_id is None:
                    run_id = f"job-{job.get('job_id')}-error"
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

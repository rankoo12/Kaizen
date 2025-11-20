from fastapi import FastAPI

# OpenTelemetry Phase 0 bootstrap (safe/no-op if deps missing)
_OTEL_ENABLED = False
_OTEL_TRACER = None
_OTEL_RUNS_COUNTER = None
_OTEL_RUN_HIST = None

def _init_otel(service_name: str = "kaizen-engine-api") -> None:
    global _OTEL_ENABLED, _OTEL_TRACER, _OTEL_RUNS_COUNTER, _OTEL_RUN_HIST
    if _OTEL_ENABLED:
        return
    try:
        import os
        from urllib.parse import urlparse
        import socket

        # Soft-disable by default unless explicitly enabled or endpoint is resolvable.
        def _truthy(v: str | None) -> bool:
            return str(v or "").strip().lower() in {"1", "true", "yes", "on"}

        explicitly_enabled = _truthy(os.environ.get("KAIZEN_OTEL_ENABLED"))
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
        host_to_check = None
        try:
            u = urlparse(endpoint)
            host_to_check = u.hostname or None
            port_to_check = u.port or (4318 if (u.scheme or "http").startswith("http") else 4317)
        except Exception:
            host_to_check = None
            port_to_check = 4318

        if not explicitly_enabled:
            try:
                if not host_to_check:
                    # No clear host -> disable
                    return
                # Quick DNS check; if fails, skip instrumentation to avoid noisy exporter errors
                socket.getaddrinfo(host_to_check, port_to_check)
            except Exception:
                return

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
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        res = Resource.create({"service.name": service_name})

        # Traces
        tp = TracerProvider(resource=res)
        span_exporter = OTLPHTTPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        tp.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tp)
        _OTEL_TRACER = trace.get_tracer("kaizen.engine.api")

        # Metrics
        metric_exporter = OTLPHTTPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
        reader = PeriodicExportingMetricReader(metric_exporter)
        mp = MeterProvider(resource=res, metric_readers=[reader])
        metrics.set_meter_provider(mp)
        meter = metrics.get_meter("kaizen.engine.api")
        _OTEL_RUNS_COUNTER = meter.create_counter(
            name="kaizen_runs_total",
            description="Total number of runs",
        )
        _OTEL_RUN_HIST = meter.create_histogram(
            name="kaizen_run_duration_seconds",
            unit="s",
            description="Duration of runs in seconds",
        )

        # Client/server auto-instrumentation
        RequestsInstrumentor().instrument()
        # FastAPIInstrumentor.instrument_app will be called in create_app once app exists

        _OTEL_ENABLED = True
    except Exception:
        # Degrade silently when OTel deps/config are unavailable
        _OTEL_ENABLED = False
        _OTEL_TRACER = None
        _OTEL_RUNS_COUNTER = None
        _OTEL_RUN_HIST = None
from engine.api.routes.resolve import register_resolve_routes
from engine.api.routes.system import router as system_router
from engine.api.routes.metrics import router as metrics_router
from engine.api.routes.runs import register_run_routes
from engine.api.routes.suites import register_suite_routes
from engine.api.routes.tests import register_test_routes
from engine.api.routes.queue import register_queue_routes
from engine.api.routes.artifacts import router as artifacts_router
from engine.api.routes.admin import router as admin_router
from engine.api.routes.profiles import router as profiles_router
from engine.api.routes.plan import router as plan_router
from engine.core.config.container import Container


def create_app(resolver=None) -> FastAPI:
    # Initialize OpenTelemetry once per process
    _init_otel("kaizen-engine-api")
    app = FastAPI(
        title="Kaizen Engine API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        max_request_size=10 * 1024 * 1024,
    )

    if resolver is None:
        container = Container()
        resolver = container.element_resolver()
        # Ensure reporter backend is wired globally for routes and reused by orchestrator.
        # If tests or callers already seeded RUN_REPORTER, reuse it instead of replacing.
        import engine.core.reporting.reporter as reporter_mod
        try:
            reporter = reporter_mod.RUN_REPORTER
        except Exception:
            reporter = None
        if reporter is None:
            reporter = container.reporter()
        reporter_mod.RUN_REPORTER = reporter
        orchestrator = container.orchestrator(reporter=reporter)

        # Wrap orchestrator run methods to emit a single run span + metrics
        if _OTEL_ENABLED and orchestrator is not None:
            import time as _time
            from opentelemetry import trace as _trace
            from opentelemetry.trace import Status, StatusCode

            _tracer = _OTEL_TRACER or _trace.get_tracer("kaizen.engine.api")

            def _wrap(fn, mode_value: str):
                def _inner(*args, **kwargs):
                    start = _time.time()
                    with _tracer.start_as_current_span("kaizen.run") as span:
                        try:
                            span.set_attribute("mode", mode_value)
                        except Exception:
                            pass
                        run_id = None
                        try:
                            run_id = fn(*args, **kwargs)
                            try:
                                span.set_attribute("run_id", str(run_id))
                            except Exception:
                                pass
                            return run_id
                        except Exception as e:  # propagate after tagging span
                            try:
                                span.set_status(Status(StatusCode.ERROR, str(e)))
                            except Exception:
                                pass
                            raise
                        finally:
                            dur = _time.time() - start
                            try:
                                attrs = {"mode": mode_value}
                                # Attempt to tag with tenant_id when resolvable
                                try:
                                    st = getattr(orchestrator, "_storage", None)
                                    if st is not None and hasattr(st, "get_run") and run_id:
                                        row = st.get_run(str(run_id))
                                        if isinstance(row, dict) and row.get("tenant_id"):
                                            attrs["tenant"] = str(row.get("tenant_id"))
                                except Exception:
                                    pass
                                if _OTEL_RUNS_COUNTER:
                                    _OTEL_RUNS_COUNTER.add(1, attributes=attrs)
                                if _OTEL_RUN_HIST:
                                    _OTEL_RUN_HIST.record(dur, attributes=attrs)
                            except Exception:
                                pass

                return _inner

            try:
                if hasattr(orchestrator, "run_live"):
                    orchestrator.run_live = _wrap(orchestrator.run_live, "live")
                if hasattr(orchestrator, "run_snapshot"):
                    orchestrator.run_snapshot = _wrap(orchestrator.run_snapshot, "snapshot")
            except Exception:
                pass

    # Register routes
    register_resolve_routes(app, resolver)
    app.include_router(system_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(plan_router)
    app.include_router(admin_router)
    app.include_router(profiles_router)
    app.include_router(artifacts_router)
    # Register run endpoints using the orchestrator
    try:
        register_run_routes(app, orchestrator)
        register_suite_routes(app, orchestrator)
        register_test_routes(app, orchestrator)
        register_queue_routes(app)
    except NameError:
        # In case a custom resolver was injected without container
        pass

    # FastAPI server instrumentation
    try:
        if _OTEL_ENABLED:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8080)

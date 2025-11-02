from __future__ import annotations

def test_reporter_increment_exists_and_is_noop_without_otel():
    # Ensure increment() exists and does not raise when OTel is absent
    from engine.core.reporting.reporter import RUN_REPORTER

    for name in (
        "healer_attempts_total",
        "healer_successes_total",
        "profile_hits_total",
        "profile_misses_total",
        "executor_step_total",
    ):
        RUN_REPORTER.increment(name, {"tool": "click"})

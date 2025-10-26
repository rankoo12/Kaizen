from engine.api.routes.metrics import get_metrics_summary
from engine.core.reporting import reporter as reporter_mod
from engine.core.reporting.reporter import RUN_REPORTER


def test_metrics_summary_merges_file_and_runs(monkeypatch):
    # Reset in-memory reporter
    RUN_REPORTER._runs.clear()
    RUN_REPORTER._open.clear()

    # Ensure API and test use the same reporter instance
    reporter_mod.RUN_REPORTER = RUN_REPORTER

    # Simulate one live run with some reasons and heal stats
    RUN_REPORTER.on_run_start("run-1", mode="live", planner="glue")
    # add a step for by_tool bucket
    RUN_REPORTER.on_step({"run_id": "run-1", "tool": "click", "reason": "not_visible"})
    RUN_REPORTER.on_run_finish(
        "run-1",
        {
            "reasons": {"none": 2, "not_visible": 1},
            "heal_attempts": 1,
            "heal_successes": 1,
            "healed_rate": 1.0,
            "planner": "glue",
            "planner_fallbacks": 0,
        },
    )

    # Stub file-based metrics
    from engine.core.metrics import collector

    monkeypatch.setattr(
        collector.metrics,
        "as_dict",
        lambda: {"runs_total": 5, "runs_failed": 1, "average_duration": 0.25},
        raising=True,
    )

    data = get_metrics_summary(window=None)
    # file-based counters present
    assert data["runs_total"] == 5 and data["runs_failed"] == 1
    # in-memory rollups present
    assert data["runs"] == 1
    assert data["reasons"]["none"] == 2 and data["reasons"]["not_visible"] == 1
    assert data["heal_attempts"] == 1 and data["heal_successes"] == 1
    assert data["planner_usage"]["glue"] == 1
    assert data["modes"]["live"] == 1
    assert data["metrics_schema"] == 1
    # by_tool grouping reflects the step event
    assert data["by_tool"]["click"]["not_visible"] == 1

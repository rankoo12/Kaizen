from engine.api.routes.metrics import get_runs_metrics
from engine.core.reporting import reporter as reporter_mod
from engine.core.reporting.reporter import RUN_REPORTER


def test_metrics_rollups_basic():
    # Reset store
    RUN_REPORTER._runs.clear()
    RUN_REPORTER._open.clear()

    # Ensure API and test use the same reporter instance
    reporter_mod.RUN_REPORTER = RUN_REPORTER

    # Simulate two runs
    RUN_REPORTER.on_run_start("run-1", mode="live", planner="glue")
    # Emit one step to populate by_tool grouping
    RUN_REPORTER.on_step({"run_id": "run-1", "tool": "click", "reason": "none"})
    RUN_REPORTER.on_run_finish(
        "run-1",
        {
            "reasons": {"none": 1, "timeout_resolve": 1},
            "heal_attempts": 2,
            "heal_successes": 1,
            "healed_rate": 0.5,
            "planner": "glue",
            "planner_fallbacks": 0,
        },
    )

    RUN_REPORTER.on_run_start("run-2", mode="snapshot", planner="glue")
    RUN_REPORTER.on_run_finish(
        "run-2",
        {
            "reasons": {"none": 2},
            "heal_attempts": 0,
            "heal_successes": 0,
            "healed_rate": 0.0,
            "planner": "glue",
            "planner_fallbacks": 0,
        },
    )

    data = get_runs_metrics(window=None)
    assert data["runs"] == 2
    assert data["reasons"]["none"] == 3
    assert data["heal_attempts"] == 2
    assert data["heal_successes"] == 1
    assert 0.0 <= data["healed_rate"] <= 1.0
    assert data["planner_usage"]["glue"] == 2
    assert data["modes"]["live"] == 1 and data["modes"]["snapshot"] == 1
    assert data["metrics_schema"] == 1
    # by_tool grouping includes our emitted step
    assert data["by_tool"]["click"]["none"] == 1

    # Window query: last run only (snapshot)
    w = get_runs_metrics(window=1)
    assert w["runs"] == 1
    assert w["modes"]["snapshot"] == 1
    assert w["reasons"]["none"] == 2


def test_metrics_rollups_profile_counters():
    from engine.core.reporting.reporter import RUN_REPORTER
    import engine.core.reporting.reporter as reporter_mod
    # Reset store and ensure shared instance
    RUN_REPORTER._runs.clear()
    RUN_REPORTER._open.clear()
    reporter_mod.RUN_REPORTER = RUN_REPORTER

    RUN_REPORTER.on_run_start("r-prof", mode="live", planner="glue")
    RUN_REPORTER.on_run_finish(
        "r-prof",
        {
            "reasons": {"none": 1},
            "heal_attempts": 3,
            "heal_successes": 1,
            "healed_rate": 1/3,
            "planner": "glue",
            "planner_fallbacks": 0,
            "profile_hits": 1,
            "profile_misses": 2,
        },
    )
    data = get_runs_metrics(window=None)
    assert data["profile_hits"] == 1
    assert data["profile_misses"] == 2

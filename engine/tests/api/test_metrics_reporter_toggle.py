import json
from pathlib import Path

import engine.core.reporting.reporter as reporter_mod
from engine.api.routes.metrics import get_runs_metrics
from engine.core.reporting.reporter import JsonlTailReporter


def test_jsonl_tail_reporter_rollups(tmp_path):
    events = tmp_path / "runs_events.jsonl"
    # Swap reporter to JSONL tailer pointing at temp file
    rep = JsonlTailReporter(events_path=events, resync_on_start=True)
    reporter_mod.RUN_REPORTER = rep

    # Append minimal events directly (simulate another process)
    lines = [
        {"type": "start", "run_id": "r1", "mode": "live"},
        {"type": "step", "run_id": "r1", "tool": "click", "reason": "none"},
        {
            "type": "finish",
            "run_id": "r1",
            "stats": {
                "reasons": {"none": 1},
                "heal_attempts": 0,
                "heal_successes": 0,
                "healed_rate": 0.0,
                "planner": "glue",
                "planner_fallbacks": 0,
            },
        },
    ]
    events.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")

    data = get_runs_metrics(window=None)
    assert data["runs"] == 1
    assert data["reasons"]["none"] == 1
    assert data["modes"]["live"] == 1

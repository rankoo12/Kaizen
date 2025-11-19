from __future__ import annotations

from engine.eval.planner_dataset import build_dataset_from_traces


def test_build_dataset_from_traces_basic():
    records = [
        {
            "event": "planner.step",
            "run_id": "run-1",
            "step_index": 0,
            "planner_path": "glue",
            "text": "go back",
            "tools": [{"tool": "back", "args": {}}],
        },
        {
            "event": "planner.step",
            "run_id": "run-1",
            "step_index": 1,
            "planner_path": "glue",
            "text": "submit the form",
            "tools": [{"tool": "press", "args": {"key": "Enter"}}],
        },
        # Non-planner event should be ignored
        {
            "event": "other",
            "run_id": "run-1",
        },
    ]

    ds = build_dataset_from_traces(records)
    assert len(ds) == 2
    ex0 = ds[0]
    ex1 = ds[1]
    assert ex0["id"] == "run-1-0"
    assert ex0["text"] == "go back"
    assert ex0["planner_path"] == "glue"
    assert ex0["tool_names"] == ["back"]
    assert ex1["id"] == "run-1-1"
    assert ex1["tool_names"] == ["press"]

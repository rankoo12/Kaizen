from __future__ import annotations

import json

from engine.eval.planner_dataset import build_training_examples


def test_build_training_examples_schema_and_content():
    curated = [
        {
            "id": "run-1-0",
            "text": "go back",
            "planner_path": "glue",
            "category": "nav",
            "tool_names": ["back"],
            "tools": [{"tool": "back", "args": {}}],
        },
        {
            "id": "run-1-1",
            "text": "assert that 'Invalid password' is shown",
            "planner_path": "glue",
            "category": "errors",
            "tool_names": ["assertText"],
            "tools": [
                {
                    "tool": "assertText",
                    "args": {
                        "target": {"text": "Invalid password"},
                        "expected": "Invalid password",
                        "match": "contains",
                    },
                }
            ],
        },
    ]
    out = build_training_examples(curated)
    assert len(out) == 2
    ex0 = out[0]
    ex1 = out[1]
    # Schema: only id/input/output/category keys are required
    for ex in out:
        assert isinstance(ex.get("input"), str) and ex["input"]
        assert isinstance(ex.get("output"), str) and ex["output"].startswith("[")
        assert isinstance(ex.get("category"), str)
    # Content: output JSON decodes to the original tools
    tools0 = json.loads(ex0["output"])
    tools1 = json.loads(ex1["output"])
    assert tools0[0]["tool"] == "back"
    assert tools1[0]["tool"] == "assertText"
    assert tools1[0]["args"]["expected"] == "Invalid password"

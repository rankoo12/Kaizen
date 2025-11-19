from __future__ import annotations

from engine.eval.planner_dataset import curate_examples, split_train_dev


def test_curate_examples_normalizes_and_deduplicates():
    raw = [
        {
            "id": "run-1-0",
            "text": "  assert that  'Invalid password'  is shown  ",
            "planner_path": "glue",
            "tool_names": ["assertText"],
            "tools": [{"tool": "assertText", "args": {"expected": "Invalid password"}}],
        },
        # duplicate text/tools with different id should be dropped
        {
            "id": "run-2-3",
            "text": "assert that 'Invalid password' is shown",
            "planner_path": "glue",
            "tool_names": ["assertText"],
            "tools": [{"tool": "assertText", "args": {"expected": "Invalid password"}}],
        },
        # different tools/text should be kept
        {
            "id": "run-3-1",
            "text": "go back",
            "planner_path": "glue",
            "tool_names": ["back"],
            "tools": [{"tool": "back", "args": {}}],
        },
    ]
    curated = curate_examples(raw)
    # duplicates removed
    assert len(curated) == 2
    texts = {ex["text"] for ex in curated}
    assert "assert that 'Invalid password' is shown" in texts
    assert "go back" in texts
    # categories inferred
    cats = {ex["category"] for ex in curated}
    assert "errors" in cats or "asserts" in cats


def test_split_train_dev_stride():
    examples = [
        {"id": f"ex-{i}", "text": f"t{i}", "tool_names": ["click"], "tools": [{"tool": "click"}]}
        for i in range(10)
    ]
    train, dev = split_train_dev(examples, dev_every=3)
    assert len(train) + len(dev) == len(examples)
    # With dev_every=3, indices 0,3,6,9 go to dev
    assert len(dev) == 4
    dev_ids = {ex["id"] for ex in dev}
    assert "ex-0" in dev_ids and "ex-3" in dev_ids

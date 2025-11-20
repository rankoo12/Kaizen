from __future__ import annotations

from pathlib import Path

from engine.eval.pagebrain_ranker import evaluate_baseline, train_and_eval


def test_evaluate_baseline_counts_correct():
    examples = [
        {
            "label": 0,
            "candidates": [
                {"rank": 0, "selector": {"type": "css", "value": "#a"}, "visible": True, "enabled": True},
                {"rank": 1, "selector": {"type": "css", "value": "#b"}, "visible": True, "enabled": True},
            ],
        },
        {
            "label": 1,
            "candidates": [
                {"rank": 0, "selector": {"type": "css", "value": "#c"}, "visible": True, "enabled": True},
                {"rank": 1, "selector": {"type": "css", "value": "#d"}, "visible": True, "enabled": True},
            ],
        },
    ]
    metrics = evaluate_baseline(examples)
    assert metrics["total"] == 2
    assert metrics["correct"] >= 1  # at least one top1 correct
    assert metrics["topk_accuracy"] >= metrics["top1_accuracy"]


def test_train_and_eval_handles_missing_files(tmp_path: Path, monkeypatch):
    # point to empty dirs to ensure graceful handling
    monkeypatch.chdir(tmp_path)
    train_path = Path("train_missing.jsonl")
    dev_path = Path("dev_missing.jsonl")
    metrics = train_and_eval(train_path, dev_path)
    assert metrics["train"]["total"] == 0
    assert metrics["dev"]["total"] == 0

from __future__ import annotations

from pathlib import Path

from engine.eval.pagebrain_ranker import evaluate_baseline, train_and_eval


def test_evaluate_baseline_counts_correct():
    examples = [{"pagebrain": {"chosen": {"selector": {"type": "css", "value": "#a"}}}} for _ in range(3)]
    metrics = evaluate_baseline(examples)
    assert metrics["total"] == 3
    assert metrics["correct"] == 3
    assert metrics["top1_accuracy"] == 1.0


def test_train_and_eval_handles_missing_files(tmp_path: Path, monkeypatch):
    # point to empty dirs to ensure graceful handling
    monkeypatch.chdir(tmp_path)
    train_path = Path("train_missing.jsonl")
    dev_path = Path("dev_missing.jsonl")
    metrics = train_and_eval(train_path, dev_path)
    assert metrics["train"]["total"] == 0
    assert metrics["dev"]["total"] == 0

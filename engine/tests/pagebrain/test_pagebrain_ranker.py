from __future__ import annotations

from pathlib import Path

from engine.eval.pagebrain_ranker import evaluate_baseline, train_and_eval


def test_evaluate_baseline_counts_correct():
    def _cand(value, rank):
        return {
            "rank": rank,
            "selector": {"type": "css", "value": value},
            "visible": True,
            "enabled": True,
            "features": {
                "rank": rank,
                "selector_len": float(len(value)),
                "has_id": 1.0 if "#" in value else 0.0,
                "has_class": 1.0 if "." in value else 0.0,
                "has_attr": 0.0,
                "num_desc": 0.0,
                "visible": 1.0,
                "enabled": 1.0,
                "type_is_css": 1.0,
                "type_is_xpath": 0.0,
            },
        }

    examples = [
        {
            "label": 0,
            "candidates": [
                _cand("#a", 0),
                _cand("#b", 1),
            ],
        },
        {
            "label": 1,
            "candidates": [
                _cand("#c", 0),
                _cand("#d", 1),
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

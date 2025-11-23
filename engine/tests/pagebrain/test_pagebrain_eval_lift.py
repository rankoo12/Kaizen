from __future__ import annotations

from pathlib import Path

from engine.eval.pagebrain_ranker import compute_lift


def _cand(value: str, rank: int) -> dict:
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


def test_compute_lift_handles_small_dataset(tmp_path: Path):
    train_path = tmp_path / "train.jsonl"
    dev_path = tmp_path / "dev.jsonl"
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
    for path in (train_path, dev_path):
        with path.open("w", encoding="utf-8") as fp:
            for ex in examples:
                import json

                fp.write(json.dumps(ex) + "\n")

    metrics = compute_lift(train_path, dev_path)
    assert "baseline" in metrics and "dev" in metrics and "lift" in metrics
    assert metrics["baseline"]["total"] == 2
    assert metrics["dev"]["total"] == 2
    lift = metrics["lift"]
    for key in ("top1_accuracy", "topk_accuracy", "mrr"):
        assert key in lift

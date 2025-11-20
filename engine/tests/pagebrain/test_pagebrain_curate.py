from __future__ import annotations

import json
from pathlib import Path

from scripts import pagebrain_curate_dataset


def test_pagebrain_curate_filters_and_splits(tmp_path: Path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(pagebrain_curate_dataset, "REPORTS", reports)

    src = reports / "pagebrain_dataset.jsonl"
    data = [
        {
            "example_id": "ok-1",
            "ok": True,
            "label": 0,
            "candidates": [{"selector": {"type": "css", "value": "#a"}}],
        },
        {
            "example_id": "bad-1",
            "ok": False,
            "label": 0,
            "candidates": [{"selector": {"type": "css", "value": "#b"}}],
        },
        {
            "example_id": "bad-2",
            "ok": True,
            "label": None,
            "candidates": [{"selector": {"type": "css", "value": "#c"}}],
        },
    ]
    with src.open("w", encoding="utf-8") as fp:
        for ex in data:
            fp.write(json.dumps(ex) + "\n")

    rc = pagebrain_curate_dataset.main()
    assert rc == 0

    train = (reports / "pagebrain_train.jsonl").read_text(encoding="utf-8").strip().splitlines()
    dev = (reports / "pagebrain_dev.jsonl").read_text(encoding="utf-8").strip().splitlines()
    # Only one good example; it lands in dev (idx 0)
    assert len(train) == 0
    assert len(dev) == 1
    assert json.loads(dev[0])["example_id"] == "ok-1"

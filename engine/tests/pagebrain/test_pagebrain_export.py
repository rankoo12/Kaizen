from __future__ import annotations

import json
from pathlib import Path

from engine.core.logging.log import RunJsonlLogger
from scripts import pagebrain_export_dataset


def test_pagebrain_export_reads_choice_events(tmp_path: Path, monkeypatch):
    logs_dir = tmp_path / "logs"
    reports_dir = tmp_path / "reports"
    logs_dir.mkdir()
    reports_dir.mkdir()

    # Patch module paths
    monkeypatch.setattr(pagebrain_export_dataset, "LOGS", logs_dir)
    monkeypatch.setattr(pagebrain_export_dataset, "REPORTS", reports_dir)

    # Write a fake action.run event with pagebrain metadata
    logger = RunJsonlLogger(run_id="run-test", logs_dir=logs_dir)
    logger.info(
        "action.run",
        run_id="run-test",
        tool="click",
        ok=True,
        reason=None,
        target_signature={"type": "css", "value": "#login"},
        executor={"status": "passed"},
        pagebrain={
            "candidate_count": 2,
            "chosen": {"selector": {"type": "css", "value": "#login"}},
            "candidates": [
                {"rank": 0, "selector": {"type": "css", "value": "#login"}},
                {"rank": 1, "selector": {"type": "css", "value": "#foo"}},
            ],
        },
    )
    logger.close()

    rc = pagebrain_export_dataset.main()
    assert rc == 0

    out_path = reports_dir / "pagebrain_dataset.jsonl"
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    ex = json.loads(lines[0])
    assert ex["run_id"] == "run-test"
    assert ex["tool"] == "click"
    assert ex["ok"] is True
    assert ex["candidate_count"] == 2
    assert ex["label"] == 0
    assert len(ex["candidates"]) == 2
    assert ex["candidates"][0]["selector"]["value"] == "#login"

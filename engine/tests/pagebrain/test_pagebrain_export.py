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

    # Write a fake pagebrain.choice event
    logger = RunJsonlLogger(run_id="run-test", logs_dir=logs_dir)
    logger.info(
        "pagebrain.choice",
        run_id="run-test",
        tool="click",
        ok=True,
        reason=None,
        target_signature={"type": "css", "value": "#login"},
        pagebrain={"candidate_count": 1, "chosen": {"selector": {"type": "css", "value": "#login"}}},
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
    assert ex["pagebrain"]["candidate_count"] == 1
    assert ex["pagebrain"]["chosen"]["selector"]["value"] == "#login"

from __future__ import annotations

import json
from pathlib import Path

from engine.core.logging.log import RunJsonlLogger
from scripts import run_results_export


def test_run_results_export_reads_action_events(tmp_path: Path, monkeypatch):
    logs_dir = tmp_path / "logs"
    reports_dir = tmp_path / "reports"
    logs_dir.mkdir()
    reports_dir.mkdir()

    # Patch module paths
    monkeypatch.setattr(run_results_export, "LOGS", logs_dir)
    monkeypatch.setattr(run_results_export, "REPORTS", reports_dir)

    # Write a fake action.run event with pagebrain and healer metadata
    logger = RunJsonlLogger(run_id="run-abc", logs_dir=logs_dir)
    logger.info(
        "action.run",
        run_id="run-abc",
        index=0,
        tool="click",
        ok=True,
        reason=None,
        semantic_target={"text": "Login"},
        target_signature={"type": "css", "value": "#login"},
        executor={
            "status": "passed",
            "reason": None,
            "selector": {"type": "css", "value": "#login"},
            "signature": {"type": "css", "value": "#login"},
        },
        pagebrain={"candidate_count": 1},
        healer=None,
    )
    logger.close()

    rc = run_results_export.main()
    assert rc == 0

    out_path = reports_dir / "run_results.jsonl"
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    run_obj = json.loads(lines[0])
    assert run_obj["run_id"] == "run-abc"
    assert run_obj["status"] == "passed"
    assert isinstance(run_obj.get("actions"), list) and len(run_obj["actions"]) == 1
    act = run_obj["actions"][0]
    assert act["tool"] == "click"
    assert act["semantic_target"]["text"] == "Login"
    assert act["executor"]["status"] == "passed"
    assert act["target_signature"]["value"] == "#login"

import json
from pathlib import Path

from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.orchestrator.types import IPlanner
from engine.core.logging.log import JsonlLogger
from engine.core.config.settings import settings as settings_obj


class DummyPlanner(IPlanner):
    def plan(self, step_text: str):
        from engine.core.orchestrator.types import StepPlan

        return StepPlan(target_query={"text": step_text})


def fake_resolve_snapshot(**kwargs):
    # Minimal deterministic fake resolve result
    return {
        "candidates": [{"selector": "#login", "score": 0.99}],
        "reason": "unit-fake",
    }


def test_snapshot_runner_persists_artifacts(tmp_path, monkeypatch):
    # Redirect snapshots + logs to a temporary folder (no repo pollution)
    monkeypatch.setattr(
        settings_obj, "SNAPSHOTS_DIR", Path(tmp_path / "snapshots"), raising=True
    )
    monkeypatch.setattr(settings_obj, "LOGS_DIR", Path(tmp_path / "logs"), raising=True)

    runner = SnapshotRunner(
        planner=DummyPlanner(),
        resolve_snapshot=fake_resolve_snapshot,
        storage=None,
        log=JsonlLogger(logs_dir=settings_obj.LOGS_DIR),
    )

    html = tmp_path / "page.html"
    html.write_text(
        "<html><body><button id='login'>Login</button></body></html>", encoding="utf-8"
    )

    spec = {
        "suite": "ut",
        "name": "persist",
        "steps": [
            {"text": "click login"},
            {"text": "assert login visible"},
        ],
    }

    # New behavior: run() returns run_id (string). We validate artifacts on disk.
    run_id = runner.run(spec=spec, html_path=str(html))
    assert isinstance(run_id, str) and len(run_id) > 0

    # Artifact directory
    art = Path(settings_obj.SNAPSHOTS_DIR) / "ut" / "persist"
    assert art.exists(), "Artifact directory should be created"

    # steps.jsonl should exist with exactly 2 lines (for 2 steps)
    steps_file = art / "steps.jsonl"
    assert steps_file.exists(), "steps.jsonl should be written"
    lines = steps_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "steps.jsonl should contain two records"
    r0 = json.loads(lines[0])
    assert r0["step_index"] == 0
    assert r0["action"] == "click login"
    assert r0["run_id"] == run_id

    # resolve.json summary should exist and include minimal expected fields
    resolve_file = art / "resolve.json"
    assert resolve_file.exists(), "resolve.json should be written"
    summary_json = json.loads(resolve_file.read_text(encoding="utf-8"))
    assert summary_json.get("suite") == "ut"
    assert summary_json.get("test") == "persist"
    assert summary_json.get("steps") == 2
    assert summary_json.get("run_id") == run_id
    assert summary_json.get("results")
    assert summary_json["results"][0]["candidates"][0]["selector"] == "#login"

    # input.html should be copied for traceability
    assert (art / "input.html").exists(), "input.html should be copied into artifacts"

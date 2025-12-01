from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from engine.api.server import create_app
from engine.core.logging.log import RunJsonlLogger


def _client_with_logs(monkeypatch, tmp_logs: Path) -> TestClient:
    # Point settings.LOGS_DIR at our temp dir and keep module-level alias in sync
    import engine.core.config.settings as settings_mod
    import engine.api.routes.runs as runs_mod

    try:
        monkeypatch.setattr(settings_mod.settings, "LOGS_DIR", tmp_logs, raising=False)
    except TypeError:
        # Pydantic v2: settings may be immutable; ignore if so
        pass
    monkeypatch.setattr(runs_mod, "_settings", settings_mod.settings, raising=False)
    return TestClient(create_app())


def test_run_annotations_roundtrip(tmp_path: Path, monkeypatch):
    run_id = "run-annot-1"
    tmp_logs = tmp_path / "logs"
    tmp_logs.mkdir(parents=True, exist_ok=True)

    # Seed a minimal action.run event so /api/runs/{id}/details has an action timeline
    logger = RunJsonlLogger(run_id=run_id, logs_dir=tmp_logs)
    rec = {
        "ts": 123.0,
        "event": "action.run",
        "run_id": run_id,
        "index": 0,
        "tool": "click",
        "ok": True,
        "reason": None,
        "semantic_target": {"text": "Login"},
        "target_signature": {"type": "css", "value": "#login"},
        "executor": {
            "status": "passed",
            "reason": None,
            "selector": {"type": "css", "value": "#login"},
            "signature": {"type": "css", "value": "#login"},
        },
        "pagebrain": {"candidate_count": 1},
        "healer": None,
    }
    logger._write("INFO", "action.run", **rec)
    logger.close()

    client = _client_with_logs(monkeypatch, tmp_logs)

    # Seed minimal run summary via reporter so base run exists
    import engine.core.reporting.reporter as reporter_mod

    rep = reporter_mod.RUN_REPORTER
    rep._runs.clear()
    rep._open.clear()
    rep._runs.append({"run_id": run_id, "mode": "live", "started": 100.0, "stats": {"total": 1}})

    # Create an annotation via API
    resp = client.post(
        f"/api/runs/{run_id}/annotations",
        json={"action_index": 0, "label": "passed", "source": "human_truth", "notes": "looks good"},
    )
    assert resp.status_code == 200, resp.text
    ann = resp.json()
    assert ann["run_id"] == run_id
    assert ann["action_index"] == 0
    assert ann["label"] == "passed"
    assert ann["source"] == "human_truth"

    # Fetch annotations list
    resp = client.get(f"/api/runs/{run_id}/annotations")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    anns = data.get("annotations") or []
    assert any(a.get("label") == "passed" for a in anns)

    # Run details should include annotation per action
    resp = client.get(f"/api/runs/{run_id}/details")
    assert resp.status_code == 200, resp.text
    details = resp.json()
    actions = details.get("actions") or []
    assert len(actions) == 1
    act0 = actions[0]
    assert act0["action_index"] == 0
    assert act0.get("annotation", {}).get("label") == "passed"

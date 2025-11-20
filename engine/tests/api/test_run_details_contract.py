from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from engine.api.server import create_app


def _write_action_log(tmp_logs: Path, run_id: str) -> None:
    tmp_logs.mkdir(parents=True, exist_ok=True)
    path = tmp_logs / f"run-{run_id}.jsonl"
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
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")


def _client_with_logs(monkeypatch, tmp_logs: Path) -> TestClient:
    # Point settings.LOGS_DIR at our temp dir and keep module-level alias in sync
    import engine.core.config.settings as settings_mod
    import engine.api.routes.runs as runs_mod

    # Adjust LOGS_DIR on the shared settings object
    try:
        monkeypatch.setattr(settings_mod.settings, "LOGS_DIR", tmp_logs, raising=False)
    except TypeError:
        # Pydantic v2: settings is immutable; fall back to env override if needed
        pass
    # Ensure routes module sees the same settings instance
    monkeypatch.setattr(runs_mod, "_settings", settings_mod.settings, raising=False)
    return TestClient(create_app())


def test_run_details_includes_action_timeline(tmp_path, monkeypatch):
    run_id = "run-details-1"
    tmp_logs = tmp_path / "logs"
    _write_action_log(tmp_logs, run_id)

    client = _client_with_logs(monkeypatch, tmp_logs)

    # Seed minimal run summary via reporter so base run exists
    import engine.core.reporting.reporter as reporter_mod

    rep = reporter_mod.RUN_REPORTER
    rep._runs.clear()
    rep._open.clear()
    rep._runs.append({"run_id": run_id, "mode": "live", "started": 100.0, "stats": {"total": 1}})

    res = client.get(f"/api/runs/{run_id}/details")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["run"]["run_id"] == run_id
    actions = data.get("actions") or []
    assert len(actions) == 1
    act = actions[0]
    assert act["tool"] == "click"
    assert act["semantic_target"]["text"] == "Login"
    assert act["executor"]["status"] == "passed"
    # error mirrors reason for contract-style consumers
    assert "error" in act["executor"]

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch, runs):
    # Ensure API uses our shared RUN_REPORTER instance and seed runs
    import engine.core.reporting.reporter as reporter_mod
    rep = reporter_mod.RUN_REPORTER
    rep._runs.clear()
    rep._open.clear()
    # Seed synthetic runs (already finished)
    for r in runs:
        rep._runs.append(r)

    from engine.api.server import create_app
    return TestClient(create_app())


def test_runs_list_basic_and_limit(monkeypatch):
    runs = [
        {"run_id": "r1", "mode": "live", "started": 100.0, "stats": {"total": 1}},
        {"run_id": "r2", "mode": "snapshot", "started": 200.0, "stats": {"total": 2}},
        {"run_id": "r3", "mode": "live", "started": 300.0, "stats": {"total": 3}},
    ]
    client = _client(monkeypatch, runs)
    r = client.get("/api/runs", params={"limit": 2})
    assert r.status_code == 200
    data = r.json()
    # Sorted desc by started: r3, r2
    ids = [x["run_id"] for x in data["runs"]]
    assert ids == ["r3", "r2"]
    assert data["total"] == 3 and data["limit"] == 2


def test_runs_list_filter_by_mode(monkeypatch):
    runs = [
        {"run_id": "a1", "mode": "live", "started": 10.0, "stats": {}},
        {"run_id": "a2", "mode": "snapshot", "started": 20.0, "stats": {}},
        {"run_id": "a3", "mode": "live", "started": 30.0, "stats": {}},
    ]
    client = _client(monkeypatch, runs)
    r = client.get("/api/runs", params={"mode": "live"})
    assert r.status_code == 200
    data = r.json()
    ids = [x["run_id"] for x in data["runs"]]
    assert ids == ["a3", "a1"]

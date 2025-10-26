from fastapi.testclient import TestClient
from engine.api.server import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_create_and_get_run_snapshot_inline_html():
    client = _client()
    payload = {
        "mode": "snapshot",
        "spec": {
            "suite": "api",
            "name": "demo",
            "id": "t-1",
            # Press-only mapping is used by orchestrator for deterministic plan
            "steps": [{"text": "press Enter"}],
        },
        # Inline HTML to keep run fully deterministic/offline
        "html": "<html><body><button id='login-btn'>Login</button></body></html>",
    }

    res = client.post("/api/runs", json=payload)
    assert res.status_code == 200, res.text
    run_id = res.json()["run_id"]
    assert isinstance(run_id, str) and len(run_id) > 0

    # Fetch run status + stats
    res2 = client.get(f"/api/runs/{run_id}")
    assert res2.status_code == 200, res2.text
    data = res2.json()
    assert data["run_id"] == run_id
    assert data["status"] in {"finished", "running"}
    assert isinstance(data.get("stats"), dict)


def test_get_unknown_run_returns_unknown():
    client = _client()
    res = client.get("/api/runs/does-not-exist")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unknown"
    assert data["stats"] == {}

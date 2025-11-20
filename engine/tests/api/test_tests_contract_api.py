from __future__ import annotations

from fastapi.testclient import TestClient

from engine.api.server import create_app


def _client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_create_and_get_test_contract_shape():
    client = _client()
    payload = {
        "id": "test_123",
        "name": "Login and see dashboard",
        "description": "Contract-style test",
        "app_base_url": "about:blank",
        "tags": ["smoke"],
        "steps": [
            {"id": "step_1", "index": 1, "text": "Open the login page.", "expected": "Login form is visible."},
            {"id": "step_2", "index": 2, "text": "Click Login.", "expected": "I am logged in."},
        ],
    }
    res = client.post("/api/tests", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["test_id"] == "test_123"

    res2 = client.get("/api/tests/test_123")
    assert res2.status_code == 200, res2.text
    got = res2.json()
    assert got["test_id"] == "test_123"
    test = got.get("test") or {}
    assert test["id"] == "test_123"
    assert [s["text"] for s in test.get("steps", [])] == [
        "Open the login page.",
        "Click Login.",
    ]


def test_run_test_live_uses_app_base_url():
    client = _client()
    payload = {
        "id": "test_live_1",
        "name": "NL live contract test",
        "app_base_url": "about:blank",
        "steps": [
            {"id": "step_1", "index": 1, "text": "press Enter"},
        ],
    }
    res = client.post("/api/tests", json=payload)
    assert res.status_code == 201, res.text

    # Run in live mode; url is taken from app_base_url
    res2 = client.post("/api/tests/test_live_1/runs", json={"mode": "live"})
    assert res2.status_code == 200, res2.text
    run_id = res2.json()["run_id"]
    assert isinstance(run_id, str) and run_id

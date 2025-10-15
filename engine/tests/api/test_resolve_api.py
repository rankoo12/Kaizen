import pytest
from fastapi.testclient import TestClient
from engine.api.server import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    return TestClient(app)


def test_resolve_endpoint_returns_candidates(client):
    payload = {
        "snapshot": {
            "html_path": "mock.html",
            "candidates": [
                {
                    "tag": "button",
                    "role": "button",
                    "text": "Login",
                    "id": "login-btn",
                    "visible": True,
                    "clickable": True,
                },
                {
                    "tag": "button",
                    "role": "button",
                    "text": "Register",
                    "visible": True,
                    "clickable": True,
                },
                {
                    "tag": "a",
                    "role": "link",
                    "text": "Login",
                    "visible": True,
                    "clickable": True,
                },
            ],
            "styles_index_path": None,
            "screenshot_path": None,
            "frames": [],
        },
        "query": {"text": "Login", "hints": {"role": "button"}},
    }

    res = client.post("/api/resolve", json=payload)
    assert res.status_code == 200, res.text

    data = res.json()
    assert "primary" in data
    assert "confidence" in data
    assert data["primary"]["value"] == "login-btn"
    assert 0.0 <= data["confidence"] <= 1.0

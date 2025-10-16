import pytest
from fastapi.testclient import TestClient
from engine.api.server import create_app


@pytest.mark.integration
def test_resolve_api_returns_200_with_minimal_valid_catalog():
    """Real resolver through the API: non-empty catalog + simple text query should resolve."""
    app = create_app()  # real DI -> real ElementResolver
    client = TestClient(app)

    payload = {
        "snapshot": {
            "html_path": "about:blank",  # not read by resolver in this path
            "candidates": [
                {
                    # keep fields generic & permissive so most scorers pass
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
            ],
            "styles_index_path": None,
            "screenshot_path": None,
            "frames": [],
        },
        "query": {
            "text": "Login",
            "hints": {"role": "button"},  # nudge scoring toward the button
            "scope": None,
        },
    }

    res = client.post("/api/resolve", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    # Minimal invariants for LocatorCandidates-like shape
    assert "primary" in body and "confidence" in body and "reason" in body

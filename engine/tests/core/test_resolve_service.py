from engine.core.api.resolve_service import resolve_snapshot


def test_resolve_snapshot_facade_returns_candidates():
    snapshot = {
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
    }
    query = {"text": "Login", "hints": {"role": "button"}}

    res = resolve_snapshot(snapshot, query)

    assert res["primary"]["value"] == "login-btn"
    assert isinstance(res["fallbacks"], list)
    assert 0.0 <= res["confidence"] <= 1.0

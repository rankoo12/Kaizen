from engine.core.resolving.element_resolver import ElementResolver
from engine.core.browser.snapshot_dto import PageSnapshot


def test_element_resolver_returns_primary_and_fallbacks():
    snapshot: PageSnapshot = {
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
    resolver = ElementResolver()
    res = resolver.resolve({"text": "Login", "hints": {"role": "button"}}, snapshot)
    assert res["primary"]["type"] in ("id", "testid", "css")
    assert isinstance(res["fallbacks"], list)
    assert res["confidence"] >= 0.0 and res["confidence"] <= 1.0
    assert "SemanticStrategy" in res["reason"]

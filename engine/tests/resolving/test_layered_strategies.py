from engine.core.resolving.element_resolver import ElementResolver


def test_layered_prefers_testid_over_text():
    r = ElementResolver()
    catalog = [
        {"tag": "button", "text": "Login", "visible": True, "enabled": True, "attrs": {"testid": "other"}},
        {"tag": "button", "text": "Sign In", "visible": True, "enabled": True, "attrs": {"testid": "login"}},
    ]
    out = r.resolve({"text": "login"}, {"candidates": catalog})
    # Prefer data-testid selector when present; locator can be a testid type
    assert out["primary"]["type"] in ("testid", "css")
    if out["primary"]["type"] == "testid":
        assert out["primary"]["value"] == "login"
    else:
        assert out["primary"]["value"] == '[data-testid="login"]'


def test_layered_radio_prefers_value_match():
    r = ElementResolver()
    catalog = [
        {"tag": "input", "type": "radio", "visible": True, "enabled": True, "value": "small"},
        {"tag": "input", "type": "radio", "visible": True, "enabled": True, "value": "large"},
    ]
    out = r.resolve({"text": "small"}, {"candidates": catalog})
    css = out["primary"]["value"]
    assert css.startswith("input") and "small" in css.lower()

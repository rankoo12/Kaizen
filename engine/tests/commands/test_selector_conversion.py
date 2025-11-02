from engine.core.commands.selector import to_selector_string


def test_to_selector_string_basic_mappings():
    assert to_selector_string({"type": "css", "value": ".btn.primary"}) == ".btn.primary"
    assert to_selector_string({"type": "id", "value": "login"}) == "#login"
    assert (
        to_selector_string({"type": "testid", "value": "submit"})
        == "[data-testid=\"submit\"]"
    )
    assert to_selector_string({"type": "text", "value": "Sign in"}) == 'text=/Sign\\ in/i'
    assert to_selector_string("#raw") == "#raw"

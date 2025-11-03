from __future__ import annotations

from engine.core.healing.selector_healer import DeterministicHealer


def test_debug_heal_success_returns_css_primary():
    h = DeterministicHealer()
    out = h.heal({"target": {"text": "[heal-success:#login]"}}, {"tool": "click"})
    assert isinstance(out, dict)
    assert out.get("primary", {}).get("type") == "css"
    assert out.get("primary", {}).get("value") == "#login"
    assert out.get("reason") == "debug_heal_success"

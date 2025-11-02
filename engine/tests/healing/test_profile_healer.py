from __future__ import annotations

from engine.core.healing.selector_healer import DeterministicHealer


class _Storage:
    def __init__(self, selector):
        self._selector = selector

    def find_locator_profile(self, *, domain, tool, target_signature):
        return self._selector


def test_healer_uses_profile_when_available():
    sel = {"type": "css", "value": "#login"}
    healer = DeterministicHealer(storage=_Storage(sel))
    out = healer.heal({"target": {"text": "login"}}, {"tool": "click"})
    assert out and out["primary"]["type"] == "css" and out["primary"]["value"] == "#login"

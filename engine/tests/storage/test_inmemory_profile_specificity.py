from __future__ import annotations

from engine.core.storage.memory import InMemoryStorage


def test_inmemory_profile_prefers_more_specific_signature():
    st = InMemoryStorage()
    # Less specific (id only), higher hits
    st.save_locator_profile(
        domain=None,
        tool="click",
        target_signature={"id": "login"},
        selector={"type": "css", "value": "#login-id"},
    )
    st.save_locator_profile(
        domain=None,
        tool="click",
        target_signature={"id": "login"},
        selector={"type": "css", "value": "#login-id"},
    )
    # More specific (id+role), fewer hits
    st.save_locator_profile(
        domain=None,
        tool="click",
        target_signature={"id": "login", "role": "button"},
        selector={"type": "css", "value": "#login-role"},
    )

    sel = st.find_locator_profile(domain=None, tool="click", target_signature={"id": "login"})
    # Should prefer the more specific stored signature (#login-role)
    assert sel == {"type": "css", "value": "#login-role"}

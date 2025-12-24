from __future__ import annotations

from engine.core.storage.memory import InMemoryStorage


def test_inmemory_profiles_domain_and_signature_matching():
    st = InMemoryStorage()
    # Global profile
    st.save_locator_profile(
        domain=None,
        tool="click",
        target_signature={"id": "global-login"},
        selector={"type": "id", "value": "global-login"},
    )
    # Domain-scoped profile
    st.save_locator_profile(
        domain="example.com",
        tool="click",
        target_signature={"id": "login", "role": "button"},
        selector={"type": "css", "value": "#login"},
    )

    # Prefer domain match
    sel = st.find_locator_profile(domain="example.com", tool="click", target_signature={"id": "login"})
    assert sel == {"type": "css", "value": "#login"}

    # Fallback to global when domain has no match
    sel2 = st.find_locator_profile(domain="other.com", tool="click", target_signature={"id": "global-login"})
    assert sel2 == {"type": "id", "value": "global-login"}

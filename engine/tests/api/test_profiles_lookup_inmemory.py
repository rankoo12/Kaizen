from __future__ import annotations

from fastapi.testclient import TestClient


def test_profiles_lookup_with_domain_inmemory(monkeypatch):
    from engine.core.config.container import InMemoryStorage

    st = InMemoryStorage()
    st.save_locator_profile(
        domain="example.com",
        tool="click",
        target_signature={"id": "login"},
        selector={"type": "css", "value": "#login"},
    )

    class _C:
        def storage(self):
            return st

    import engine.api.routes.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "Container", _C)
    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    r = client.post("/api/profiles/lookup", json={"tool": "click", "domain": "example.com", "target_signature": {"id": "login"}})
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] == {"type": "css", "value": "#login"}

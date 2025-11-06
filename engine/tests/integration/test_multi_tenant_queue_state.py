import os
import pytest
from fastapi.testclient import TestClient


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_queue_state_filters_by_tenant(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping multi-tenant test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)

    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # Create two tenants and API keys
    admin_secret = "secret123"
    monkeypatch.setenv("KAIZEN_ADMIN_SECRET", admin_secret)

    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1", "name": "Tenant 1"})
    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2", "name": "Tenant 2"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1", "api_key": "key-t1"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2", "api_key": "key-t2"})

    # Enqueue one job per tenant
    r1 = client.post("/api/queue/runs", json={"spec": {"id": "s1"}}, headers={"X-API-Key": "key-t1"})
    r2 = client.post("/api/queue/runs", json={"spec": {"id": "s2"}}, headers={"X-API-Key": "key-t2"})
    assert r1.status_code == 200 and r2.status_code == 200

    # State filtered by X-API-Key should show only own queued job
    st1 = client.get("/api/queue/state", headers={"X-API-Key": "key-t1"}).json()
    st2 = client.get("/api/queue/state", headers={"X-API-Key": "key-t2"}).json()
    assert len(st1.get("queued", [])) == 1
    assert len(st2.get("queued", [])) == 1
    assert st1["queued"][0]["job_id"] != st2["queued"][0]["job_id"]

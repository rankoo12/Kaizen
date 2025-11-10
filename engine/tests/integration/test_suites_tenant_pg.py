import os
import pytest
from fastapi.testclient import TestClient


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_suites_persist_with_tenant_and_isolation(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)
    monkeypatch.setenv("KAIZEN_MULTITENANT_ENFORCED", "true")

    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # Provision tenants and keys via admin secret
    admin_secret = "secret123"
    monkeypatch.setenv("KAIZEN_ADMIN_SECRET", admin_secret)
    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1", "name": "Tenant 1"})
    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2", "name": "Tenant 2"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1", "api_key": "key-t1"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2", "api_key": "key-t2"})

    # Create suite for t1
    r = client.post("/api/suites", headers={"X-API-Key": "key-t1"}, json={"spec": {"id": "s1", "steps": []}})
    assert r.status_code == 200

    # Fetch with t1 -> OK
    r = client.get("/api/suites/s1", headers={"X-API-Key": "key-t1"})
    assert r.status_code == 200
    assert r.json().get("suite_id") == "s1"

    # Fetch with t2 -> hidden (404)
    r = client.get("/api/suites/s1", headers={"X-API-Key": "key-t2"})
    assert r.status_code in (404, 403)

    # Fetch without key -> 401 when enforced
    r = client.get("/api/suites/s1")
    assert r.status_code == 401

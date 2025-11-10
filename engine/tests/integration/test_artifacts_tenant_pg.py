import os
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_artifacts_are_tenant_scoped(monkeypatch, tmp_path):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)
    monkeypatch.setenv("KAIZEN_MULTITENANT_ENFORCED", "true")

    # Ensure logs dir exists and is writable
    from engine.core.config.settings import settings

    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    from engine.api.server import create_app
    from engine.core.storage.postgres import PostgresStorage

    st = PostgresStorage(dsn)

    # Create tenants and API keys via admin endpoints
    app = create_app()
    client = TestClient(app)
    admin_secret = "secret123"
    monkeypatch.setenv("KAIZEN_ADMIN_SECRET", admin_secret)
    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1"})
    client.post("/api/admin/tenants", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t1", "api_key": "key-t1"})
    client.post("/api/admin/api-keys", headers={"X-Admin-Secret": admin_secret}, json={"tenant_id": "t2", "api_key": "key-t2"})

    # Insert a run for t1 and create a dummy log artifact
    run_id = "run-tenantized"
    with st._conn() as conn:  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs(run_id, test_id, tenant_id) VALUES (%s, %s, %s) ON CONFLICT (run_id) DO NOTHING",
                (run_id, "spec-1", "t1"),
            )
    # Create a small JSONL file as run artifact
    (settings.LOGS_DIR / f"run-{run_id}.jsonl").write_text(json.dumps({"hello": "world"}) + "\n", encoding="utf-8")

    # Without key -> 401
    r = client.get(f"/api/runs/{run_id}/artifacts")
    assert r.status_code == 401

    # With t2 key -> 404 (hidden across tenants)
    r = client.get(f"/api/runs/{run_id}/artifacts", headers={"X-API-Key": "key-t2"})
    assert r.status_code == 404

    # With t1 key -> 200 and contains the log artifact
    r = client.get(f"/api/runs/{run_id}/artifacts", headers={"X-API-Key": "key-t1"})
    assert r.status_code == 200
    data = r.json()
    names = [it.get("name") for it in data.get("items", [])]
    assert "log" in names

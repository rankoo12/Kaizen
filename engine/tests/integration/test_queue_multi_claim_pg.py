import os
import pytest
from fastapi.testclient import TestClient


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_pg_queue_multi_claim(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping PG multi-claim test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)
    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # Enqueue two jobs
    j1 = client.post("/api/queue/runs", json={"spec": {"id": "q1"}}).json()["job_id"]
    j2 = client.post("/api/queue/runs", json={"spec": {"id": "q2"}}).json()["job_id"]
    assert j1 != j2

    r1 = client.get("/api/queue/next").json().get("job")
    r2 = client.get("/api/queue/next").json().get("job")
    assert r1 and r2 and r1["job_id"] != r2["job_id"]

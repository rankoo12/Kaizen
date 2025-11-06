import os
import pytest
from fastapi.testclient import TestClient


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_queue_api_with_postgres(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping PG-backed queue API test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)
    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # Enqueue a run
    r = client.post("/api/queue/runs", json={"spec": {"id": "q-api"}})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert job_id

    # Claim next job
    r = client.get("/api/queue/next")
    assert r.status_code == 200
    job = r.json().get("job")
    assert job and job.get("job_id") == job_id

    # Mark running and complete
    client.post("/api/queue/running", json={"job_id": job_id, "run_id": "run-1"})
    client.post("/api/queue/complete", json={"job_id": job_id, "run_id": "run-1"})

    # State includes lists
    r = client.get("/api/queue/state")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("queued"), list)
    assert isinstance(data.get("running"), list)
    assert isinstance(data.get("completed"), list)

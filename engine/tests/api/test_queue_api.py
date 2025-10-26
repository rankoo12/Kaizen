from fastapi.testclient import TestClient
from engine.api.server import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_enqueue_and_next_job():
    client = _client()
    # Enqueue a snapshot job
    payload = {
        "mode": "snapshot",
        "spec": {"id": "q-1", "suite": "api", "name": "q", "steps": [{"text": "press Enter"}]},
        "html": "<html><body>ok</body></html>",
    }
    r = client.post("/api/queue/runs", json=payload)
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert job_id.startswith("job-")

    # Next job pops the one we just enqueued
    r2 = client.get("/api/queue/next")
    assert r2.status_code == 200
    job = r2.json()["job"]
    assert job["job_id"] == job_id

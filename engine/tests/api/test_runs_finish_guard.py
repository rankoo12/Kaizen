from fastapi.testclient import TestClient
from engine.api.server import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_finish_duplicate_run_id_rejected():
    client = _client()
    run_id = "dup-1"
    r1 = client.post(f"/api/runs/{run_id}/finish", json={"stats": {"total": 1, "passed": 1, "failed": 0, "reasons": {}}})
    assert r1.status_code == 200
    r2 = client.post(f"/api/runs/{run_id}/finish", json={"stats": {"total": 1, "passed": 1}})
    assert r2.status_code == 409

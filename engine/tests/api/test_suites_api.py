from fastapi.testclient import TestClient
from engine.api.server import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_suite_create_get_and_run_snapshot():
    client = _client()
    # Create a suite (spec has at least one simple step)
    payload = {
        "spec": {
            "id": "suite-1",
            "suite": "api",
            "name": "basic",
            "steps": [{"text": "press Enter"}],
        }
    }
    res = client.post("/api/suites", json=payload)
    assert res.status_code == 200, res.text
    suite_id = res.json()["suite_id"]
    assert suite_id == "suite-1"

    # Retrieve suite spec (what will run)
    res2 = client.get(f"/api/suites/{suite_id}")
    assert res2.status_code == 200, res2.text
    suite = res2.json()
    assert suite["suite_id"] == suite_id
    assert suite["spec"]["name"] == "basic"

    # Trigger a snapshot run from suite
    run_req = {
        "mode": "snapshot",
        "html": "<html><body><input id='q'/></body></html>",
    }
    res3 = client.post(f"/api/suites/{suite_id}/runs", json=run_req)
    assert res3.status_code == 200, res3.text
    run_id = res3.json()["run_id"]
    assert isinstance(run_id, str) and run_id

    # Verify run status endpoint reflects it
    res4 = client.get(f"/api/runs/{run_id}")
    assert res4.status_code == 200
    data = res4.json()
    assert data["run_id"] == run_id
    assert data["status"] in {"running", "finished"}


def test_suite_not_found():
    client = _client()
    res = client.get("/api/suites/missing")
    assert res.status_code == 404
    res2 = client.post("/api/suites/missing/runs", json={})
    assert res2.status_code == 404

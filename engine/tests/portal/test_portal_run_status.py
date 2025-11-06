from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeResp:
    def __init__(self, json_obj=None, content=None, status=200, headers=None):
        self._json = json_obj
        self.content = content
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def test_portal_run_status_flows(monkeypatch):
    calls = {"state": 0}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None):
            if url.endswith("/queue/state"):
                calls["state"] += 1
                # First call: queued only; Second call: running without run_id; Third call: completed with run_id
                if calls["state"] == 1:
                    return _FakeResp({"queued": [{"job_id": "job-1"}], "running": [], "completed": []})
                elif calls["state"] == 2:
                    return _FakeResp({"queued": [], "running": [{"job_id": "job-1"}], "completed": []})
                else:
                    return _FakeResp({"queued": [], "running": [], "completed": []})
            if "/queue/completed/" in url:
                return _FakeResp({"job": {"job_id": "job-1", "run_id": "run-1"}})
            if "/runs/" in url:
                return _FakeResp({"run_id": "run-1", "status": "finished", "stats": {"total": 1}})
            return _FakeResp({})

    import portal.backend.api.routes.runs as runs_mod

    monkeypatch.setattr(runs_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)

    # Queued
    r = client.get("/runs/job-1")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    # Running without run_id
    r = client.get("/runs/job-1")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    # Completed -> fetch run
    r = client.get("/runs/job-1")
    assert r.status_code == 200
    data = r.json()
    assert data["runId"] == "run-1" and data["status"] == "finished"

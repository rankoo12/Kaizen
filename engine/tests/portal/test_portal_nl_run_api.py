from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeResp:
    def __init__(self, json_obj):
        self._json = json_obj
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        assert url.endswith("/queue/runs")
        return _FakeResp({"job_id": "job-123"})


def test_portal_nl_run_enqueues_job(monkeypatch):
    import portal.backend.api.routes.tests as tests_mod

    monkeypatch.setattr(tests_mod.httpx, "Client", _FakeClient)

    # Build portal app
    from portal.backend.api import app

    client = TestClient(app)
    r = client.post(
        "/tests/nl-run",
        json={"url": "about:blank", "stepsText": "press Enter"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["jobId"] == "job-123"

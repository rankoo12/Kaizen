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

    def get(self, url, params=None, headers=None):
        assert url.endswith("/runs/run-1/details")
        return _FakeResp({"run": {"run_id": "run-1"}, "actions": []})


def test_portal_run_details_proxy(monkeypatch):
    import portal.backend.api.routes.runs as runs_mod

    monkeypatch.setattr(runs_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)
    r = client.get("/runs/run-1/details")
    assert r.status_code == 200
    data = r.json()
    assert data["run"]["run_id"] == "run-1"

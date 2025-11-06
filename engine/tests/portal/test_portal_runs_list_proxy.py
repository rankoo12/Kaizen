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

    def get(self, url, params=None):
        assert url.endswith("/runs")
        return _FakeResp({"runs": [{"run_id": "r1"}], "total": 1, "offset": 0, "limit": 50})


def test_portal_runs_list_proxy(monkeypatch):
    import portal.backend.api.routes.runs as runs_mod

    monkeypatch.setattr(runs_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)
    r = client.get("/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1 and data["runs"][0]["run_id"] == "r1"

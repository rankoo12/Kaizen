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

    def post(self, url, json=None, headers=None):
        # Creation and run endpoints are both POSTs; distinguish by path
        if url.endswith("/api/tests"):
            assert isinstance(json, dict)
            return _FakeResp({"test_id": json.get("id", "T-123")})
        if "/api/tests/" in url and url.endswith("/runs"):
            return _FakeResp({"run_id": "run-1"})
        raise AssertionError(f"unexpected URL {url}")

    def get(self, url, params=None, headers=None):
        if "/api/tests/" in url:
            return _FakeResp({"test_id": "test-123", "test": {"id": "test-123"}})
        raise AssertionError(f"unexpected URL {url}")


def test_portal_create_and_get_test_proxy(monkeypatch):
    import portal.backend.api.routes.tests as tests_mod

    monkeypatch.setattr(tests_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)
    body = {
        "id": "test-123",
        "name": "Contract test",
        "steps": [{"id": "step_1", "index": 1, "text": "press Enter"}],
    }
    r = client.post("/tests", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["testId"] == "test-123"

    r2 = client.get("/tests/test-123")
    assert r2.status_code == 200, r2.text
    got = r2.json()
    assert got["test_id"] == "test-123"


def test_portal_run_test_proxy(monkeypatch):
    import portal.backend.api.routes.tests as tests_mod

    monkeypatch.setattr(tests_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)
    r = client.post("/tests/test-123/runs", json={"mode": "live"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["runId"] == "run-1"

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


def test_portal_artifacts_list_and_blob(monkeypatch):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None):
            if url.endswith("/artifacts"):
                return _FakeResp({"items": [{"name": "log"}, {"name": "screenshot"}]})
            if "/artifacts/" in url:
                return _FakeResp(None, content=b"PNGDATA", headers={"content-type": "image/png"})
            return _FakeResp({})

    import portal.backend.api.routes.runs as runs_mod

    monkeypatch.setattr(runs_mod.httpx, "Client", _FakeClient)
    from portal.backend.api import app

    client = TestClient(app)
    r = client.get("/runs/run-1/artifacts")
    assert r.status_code == 200
    data = r.json()
    assert any(it.get("name") == "screenshot" for it in data.get("items", []))

    r = client.get("/runs/run-1/artifacts/screenshot")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "image/png"
    assert r.content == b"PNGDATA"

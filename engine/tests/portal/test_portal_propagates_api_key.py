from __future__ import annotations

from fastapi.testclient import TestClient


def test_portal_propagates_api_key_header(monkeypatch):
    captured = {"headers": []}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            captured["headers"].append((url, dict(headers or {})))
            # respond as queue enqueue
            class _R:
                status_code = 200

                def raise_for_status(self):
                    return None

                def json(self):
                    return {"job_id": "job-xyz"}

            return _R()

        def get(self, url, params=None, headers=None):
            captured["headers"].append((url, dict(headers or {})))

            class _R:
                status_code = 200

                def raise_for_status(self):
                    return None

                def json(self):
                    # Return empty runs/state/artifacts payloads
                    if url.endswith("/runs"):
                        return {"runs": [], "total": 0, "offset": 0, "limit": 50}
                    if url.endswith("/artifacts"):
                        return {"items": []}
                    return {"queued": [], "running": [], "completed": []}

            return _R()

    import portal.backend.api.routes.runs as runs_mod

    monkeypatch.setattr(runs_mod, "httpx", type("_M", (), {"Client": _FakeClient}))
    from portal.backend.api import app

    client = TestClient(app)
    # Call endpoints with X-API-Key and verify it is forwarded
    hdr = {"X-API-Key": "key-t1"}
    r = client.post("/runs", json={"spec": {"id": "s1"}}, headers=hdr)
    assert r.status_code == 200
    # expect at least one captured header tuple with X-API-Key
    assert any("X-API-Key" in h for _, h in captured["headers"])  # type: ignore

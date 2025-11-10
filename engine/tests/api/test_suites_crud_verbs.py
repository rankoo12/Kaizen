from __future__ import annotations

from fastapi.testclient import TestClient


def test_suites_crud_inmemory():
    # Use default app (no PG env), exercise PUT/PATCH/DELETE
    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # PUT creates
    r = client.put("/api/suites/sA", json={"spec": {"id": "sA", "steps": [{"text": "press enter"}]}})
    assert r.status_code == 200 and r.json()["suite_id"] == "sA"
    r = client.get("/api/suites/sA")
    assert r.status_code == 200 and r.json()["spec"]["id"] == "sA"

    # PATCH merges
    r = client.patch("/api/suites/sA", json={"spec": {"metadata": {"owner": "qa"}}})
    assert r.status_code == 200
    r = client.get("/api/suites/sA")
    data = r.json()
    assert data["spec"]["metadata"]["owner"] == "qa"

    # DELETE removes
    r = client.delete("/api/suites/sA")
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.get("/api/suites/sA")
    assert r.status_code == 404

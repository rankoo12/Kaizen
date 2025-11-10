from __future__ import annotations

import os
import time
from fastapi.testclient import TestClient


def test_queue_rate_limit_429(monkeypatch):
    # Tight window so we can trigger 429 quickly
    monkeypatch.setenv("KAIZEN_QUEUE_RATE_WINDOW_SEC", "1")
    monkeypatch.setenv("KAIZEN_QUEUE_RATE_MAX_REQUESTS", "2")

    from engine.api.server import create_app

    app = create_app()
    client = TestClient(app)

    # First two allowed
    assert client.get("/api/queue/state").status_code in (200, 401)
    assert client.get("/api/queue/state").status_code in (200, 401)
    # Third within same window -> 429
    r = client.get("/api/queue/state")
    assert r.status_code == 429

    # After window passes, should allow again
    time.sleep(1.1)
    r2 = client.get("/api/queue/state")
    assert r2.status_code in (200, 401)

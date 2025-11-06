from __future__ import annotations

import json
from fastapi.testclient import TestClient


class _FakeSettings:
    OLLAMA_MODEL = "test-model"
    PREVIEW_RATE_WINDOW_SEC = 1
    PREVIEW_RATE_MAX_REQUESTS = 1
    PREVIEW_INPUT_TEXT_MAX_CHARS = 20
    PREVIEW_CONTEXT_HTML_MAX_CHARS = 50


def _build_app_with_container(monkeypatch, fake_container):
    import engine.api.routes.plan as plan_mod

    monkeypatch.setattr(plan_mod, "Container", fake_container)
    from engine.api.server import create_app

    return create_app()


def test_rate_limit_429_on_burst(monkeypatch):
    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Non-JSON to trigger glue fallback quickly
            return "not json"

    class _C:
        def llm_text(self):
            return _FakeLLM()

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    headers = {"X-API-Key": "test-key-1"}
    r1 = client.post("/api/plan/preview", headers=headers, json={"text": "click Login"})
    assert r1.status_code == 200
    r2 = client.post("/api/plan/preview", headers=headers, json={"text": "click Login"})
    assert r2.status_code == 429

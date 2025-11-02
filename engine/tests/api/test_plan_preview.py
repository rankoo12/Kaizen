from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


class _FakeSettings:
    OLLAMA_MODEL = "test-model"


def _build_app_with_container(monkeypatch, fake_container):
    import engine.api.routes.plan as plan_mod

    monkeypatch.setattr(plan_mod, "Container", fake_container)
    from engine.api.server import create_app

    return create_app()


def test_plan_preview_returns_501_when_llm_disabled(monkeypatch):
    class _C:
        def llm_text(self):
            return None

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": "press enter"})
    assert r.status_code == 501
    assert "LLM is not enabled" in r.text


def test_plan_preview_validates_and_returns_plan(monkeypatch):
    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Minimal valid plan JSON
            return json.dumps([
                {"tool": "press", "args": {"key": "Enter"}},
            ])

    class _C:
        def llm_text(self):
            return _FakeLLM()

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": "press enter"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert isinstance(data.get("plan"), list) and data["plan"][0]["tool"] == "press"

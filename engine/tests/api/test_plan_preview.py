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


def test_plan_preview_glue_fallback_on_non_json(monkeypatch):
    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Return a non-JSON response to trigger fallback
            return "not json at all"

    class _C:
        def llm_text(self):
            return _FakeLLM()

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": "click Login"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    plan = data.get("plan")
    assert isinstance(plan, list)
    assert plan[0]["tool"] == "click"
    assert plan[0]["args"]["target"]["text"].lower() == "login"


def test_plan_preview_parses_chat_wrapper(monkeypatch):
    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Return a chat-style wrapper with message.content holding JSON
            payload = {
                "model": "x",
                "message": {
                    "role": "assistant",
                    "content": json.dumps([
                        {"tool": "click", "args": {"target": {"text": "Name"}}}
                    ]),
                },
                "done": True,
            }
            return json.dumps(payload)

    class _C:
        def llm_text(self):
            return _FakeLLM()

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": "Click the Name field"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    plan = data.get("plan")
    assert isinstance(plan, list)
    assert plan[0]["tool"] == "click"
    assert plan[0]["args"]["target"]["text"] == "Name"


def test_plan_preview_qa_flow_llm_multi_step(monkeypatch):
    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Simulate a typical QA flow over a login form:
            # type email, type password, press Enter, then assert URL
            return json.dumps(
                [
                    {"tool": "type", "args": {"target": {"text": "Email"}, "text": "user@example.com"}},
                    {"tool": "type", "args": {"target": {"text": "Password"}, "text": "secret"}},
                    {"tool": "press", "args": {"key": "Enter"}},
                    {"tool": "assertUrl", "args": {"expected": "/dashboard", "match": "contains"}},
                ]
            )

    class _C:
        def llm_text(self):
            return _FakeLLM()

        def settings(self):
            return _FakeSettings()

    app = _build_app_with_container(monkeypatch, _C)
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": "fill the login form and go to the dashboard"})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    plan = data.get("plan")
    assert isinstance(plan, list)
    assert [step["tool"] for step in plan] == ["type", "type", "press", "assertUrl"]

from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeSettings:
    OLLAMA_MODEL = "test-model"


def _build_app_with_container(monkeypatch, fake_container):
    import engine.api.routes.plan as plan_mod

    def _container_factory():
        return fake_container

    monkeypatch.setattr(plan_mod, "Container", _container_factory)
    from engine.api.server import create_app

    return create_app()


class _FakeLLM:
    def __init__(self, payload: str):
        self.payload = payload

    def ask(self, prompt: str) -> str:
        # Always return non-JSON so glue mapping is exercised
        return self.payload


class _C:
    def __init__(self, payload: str = "not json"):
        self._llm = _FakeLLM(payload)

    def llm_text(self):
        return self._llm

    def settings(self):
        return _FakeSettings()


def _preview(monkeypatch, text: str):
    app = _build_app_with_container(monkeypatch, _C())
    client = TestClient(app)
    r = client.post("/api/plan/preview", json={"text": text})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    return data["plan"]


def test_preview_go_back_uses_back_tool(monkeypatch):
    plan = _preview(monkeypatch, "go back")
    assert isinstance(plan, list)
    assert plan[0]["tool"] == "back"


def test_preview_reload_and_scroll_intents(monkeypatch):
    plan = _preview(monkeypatch, "reload the page")
    assert plan[0]["tool"] == "reload"
    plan2 = _preview(monkeypatch, "scroll down a bit")
    assert plan2[0]["tool"] == "scroll"
    assert plan2[0]["args"]["direction"] == "down"


def test_preview_tab_navigation_and_download_intents(monkeypatch):
    plan = _preview(monkeypatch, "open a new tab")
    assert isinstance(plan, list)
    assert plan[0]["tool"] == "newTab"
    plan2 = _preview(monkeypatch, "switch to tab 2")
    assert plan2[0]["tool"] == "switchTab"
    assert plan2[0]["args"].get("index") == 1
    plan3 = _preview(monkeypatch, "close this tab")
    assert plan3[0]["tool"] == "closeTab"
    plan4 = _preview(monkeypatch, "download the report")
    assert plan4[0]["tool"] == "download"
    assert plan4[0]["args"]["target"]["text"] == "the report"


def test_preview_assert_url_contains(monkeypatch):
    plan = _preview(monkeypatch, "check that the URL contains /dashboard")
    assert isinstance(plan, list)
    assert plan[0]["tool"] == "assertUrl"
    assert plan[0]["args"]["expected"] == "/dashboard"
    assert plan[0]["args"]["match"] == "contains"

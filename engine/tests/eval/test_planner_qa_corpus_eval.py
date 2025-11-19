from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from engine.eval.qa_corpus import QACase, qa_corpus


class _FakeSettings:
    OLLAMA_MODEL = "test-model"
    PREVIEW_RATE_WINDOW_SEC = 60
    PREVIEW_RATE_MAX_REQUESTS = 1000


def _build_app_with_container(monkeypatch, fake_container):
    import engine.api.routes.plan as plan_mod

    def _container_factory():
        return fake_container

    monkeypatch.setattr(plan_mod, "Container", _container_factory)
    from engine.api.server import create_app

    return create_app()


class _GlueLLM:
    def ask(self, prompt: str) -> str:
        # Always return non-JSON so glue mapping is exercised
        return "not json"


class _LLMContainer:
    def __init__(self):
        self._llm = _GlueLLM()

    def llm_text(self):
        return self._llm

    def settings(self):
        return _FakeSettings()


def _run_case(client: TestClient, case: QACase) -> tuple[bool, list[dict[str, Any]]]:
    r = client.post("/api/plan/preview", json={"text": case.text})
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    plan = data["plan"]
    tools = [step.get("tool") for step in plan]
    ok = tools[: len(case.expected_tools)] == case.expected_tools
    return ok, plan


def test_planner_qa_glue_corpus_all_pass(monkeypatch):
    app = _build_app_with_container(monkeypatch, _LLMContainer())
    client = TestClient(app)
    corpus = qa_corpus()

    total = len(corpus)
    passed = 0
    by_category: dict[str, int] = {}

    for case in corpus:
        ok, _ = _run_case(client, case)
        if ok:
            passed += 1
        by_category[case.category] = by_category.get(case.category, 0) + 1

    # Guardrail: corpus should keep growing as we expand QA coverage
    assert total >= 60
    assert passed == total  # glue should handle all of these deterministic QA intents
    # Ensure we keep coverage for key QA categories
    for required in {"nav", "scroll", "download", "asserts", "forms", "errors", "actions"}:
        assert required in by_category
    # Basic per-category minimums so we do not regress coverage silently
    assert by_category["nav"] >= 10
    assert by_category["scroll"] >= 8
    assert by_category["download"] >= 8
    assert by_category["asserts"] >= 8
    assert by_category["errors"] >= 3
    assert by_category["forms"] >= 10
    assert by_category["actions"] >= 10

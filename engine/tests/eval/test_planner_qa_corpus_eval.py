from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List

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


@dataclass
class QACase:
    case_id: str
    text: str
    expected_tools: List[str]
    category: str = "generic"


def _qa_corpus() -> list[QACase]:
    return [
        QACase(
            case_id="nav_back",
            text="go back",
            expected_tools=["back"],
            category="nav",
        ),
        QACase(
            case_id="nav_reload",
            text="reload the page",
            expected_tools=["reload"],
            category="nav",
        ),
        QACase(
            case_id="scroll_down",
            text="scroll down a bit",
            expected_tools=["scroll"],
            category="scroll",
        ),
        QACase(
            case_id="download_report",
            text="download the report",
            expected_tools=["download"],
            category="download",
        ),
        QACase(
            case_id="url_contains_dashboard",
            text="check that the URL contains /dashboard",
            expected_tools=["assertUrl"],
            category="asserts",
        ),
        QACase(
            case_id="submit_form",
            text="submit the form",
            expected_tools=["press"],
            category="forms",
        ),
    ]


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
    corpus = _qa_corpus()

    total = len(corpus)
    passed = 0
    by_category: dict[str, int] = {}

    for case in corpus:
        ok, _ = _run_case(client, case)
        if ok:
            passed += 1
        by_category[case.category] = by_category.get(case.category, 0) + 1

    assert total >= 5  # guardrail: do not shrink corpus silently
    assert passed == total  # glue should handle all of these deterministic QA intents
    # Ensure we keep coverage for key QA categories
    for required in {"nav", "scroll", "download", "asserts", "forms"}:
        assert required in by_category

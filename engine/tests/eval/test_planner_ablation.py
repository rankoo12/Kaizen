from __future__ import annotations

from fastapi.testclient import TestClient

from engine.eval.planner_ablation import PlannerExample, evaluate_examples


def test_evaluate_examples_computes_accuracy_and_by_category():
    examples = [
        PlannerExample(text="go back", expected_tools=["back"], category="nav"),
        PlannerExample(text="reload the page", expected_tools=["reload"], category="nav"),
        PlannerExample(text="download the report", expected_tools=["download"], category="download"),
        PlannerExample(text="assert that 'Invalid password' is shown", expected_tools=["assertText"], category="errors"),
    ]

    def _plan_fn_ok(text: str):
        if "go back" in text:
            return ["back"]
        if "reload" in text:
            return ["reload"]
        if "download" in text:
            return ["download"]
        if "Invalid password" in text:
            return ["assertText"]
        return []

    def _plan_fn_partial(text: str):
        if "go back" in text:
            return ["back"]
        if "reload" in text:
            return ["click"]  # wrong
        if "download" in text:
            return ["download"]
        if "Invalid password" in text:
            return ["assertText"]
        return []

    all_ok = evaluate_examples(examples, _plan_fn_ok)
    assert all_ok["total"] == 4
    assert all_ok["correct"] == 4
    assert all_ok["accuracy"] == 1.0
    assert all_ok["by_category"]["nav"]["accuracy"] == 1.0

    partial = evaluate_examples(examples, _plan_fn_partial)
    assert partial["total"] == 4
    assert partial["correct"] == 3
    assert 0.7 <= partial["accuracy"] <= 0.8
    assert partial["by_category"]["nav"]["total"] == 2
    assert partial["by_category"]["nav"]["correct"] == 1


def test_planner_ablation_uses_fake_tuned_model_via_preview(monkeypatch):
    # Small corpus reused from the pure function test
    examples = [
        PlannerExample(text="go back", expected_tools=["back"], category="nav"),
        PlannerExample(text="reload the page", expected_tools=["reload"], category="nav"),
        PlannerExample(text="download the report", expected_tools=["download"], category="download"),
        PlannerExample(
            text="assert that 'Invalid password' is shown",
            expected_tools=["assertText"],
            category="errors",
        ),
    ]

    class _FakeSettings:
        OLLAMA_MODEL = "tuned-model"
        PREVIEW_RATE_WINDOW_SEC = 60
        PREVIEW_RATE_MAX_REQUESTS = 1000

    class _FakeLLM:
        def ask(self, prompt: str) -> str:
            # Return strict JSON so we exercise the LLM JSON path, not glue.
            if "go back" in prompt:
                return '[{"tool":"back","args":{}}]'
            if "reload the page" in prompt:
                return '[{"tool":"reload","args":{}}]'
            if "download the report" in prompt:
                return '[{"tool":"download","args":{}}]'
            if "Invalid password" in prompt:
                return (
                    '[{"tool":"assertText","args":'
                    '{"target":{"text":"Invalid password"},"expected":"Invalid password","match":"contains"}}]'
                )
            # Anything else: behave like glue-eval mode to keep behavior predictable
            return "not json"

    class _FakeContainer:
        def __init__(self):
            self._llm = _FakeLLM()

        def llm_text(self):
            return self._llm

        def settings(self):
            return _FakeSettings()

    # Wire the fake container into /api/plan/preview, as eval_planner_ablation.py does.
    import engine.api.routes.plan as plan_mod  # type: ignore

    def _container_factory():
        return _FakeContainer()

    monkeypatch.setattr(plan_mod, "Container", _container_factory)
    from engine.api.server import create_app  # type: ignore

    app = create_app()
    client = TestClient(app)

    def _plan_fn(text: str):
        r = client.post("/api/plan/preview", json={"text": text})
        assert r.status_code == 200
        data = r.json()
        assert data.get("valid") is True
        plan = data.get("plan") or []
        return [
            step.get("tool")
            for step in plan
            if isinstance(step, dict) and isinstance(step.get("tool"), str)
        ]

    metrics = evaluate_examples(examples, _plan_fn)
    # Smoke-level expectations: integration works and categories are populated.
    assert metrics["total"] == len(examples)
    assert metrics["correct"] >= 1
    assert "nav" in metrics["by_category"]
    assert "download" in metrics["by_category"]
    assert "errors" in metrics["by_category"]

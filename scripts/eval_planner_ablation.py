"""
Planner LLM vs glue evaluation (P2).

Runs a small QA corpus through /api/plan/preview using:
  - glue path (LLM returns non-JSON)
  - llm path (default Container)

and prints accuracy per category for each.

Usage (from repo root, with deps installed):
  python scripts/eval_planner_ablation.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # type: ignore

from engine.eval.planner_ablation import PlannerExample, evaluate_examples  # type: ignore


@dataclass
class _FakeSettings:
    OLLAMA_MODEL: str = "eval-model"


class _GlueLLM:
    def ask(self, prompt: str) -> str:
        # Always return non-JSON so preview falls back to glue mapping
        return "not json"


class _GlueContainer:
    def __init__(self):
        from engine.core.config.container import Container as _C  # type: ignore

        self._inner = _C()
        self._llm = _GlueLLM()

    def llm_text(self):
        return self._llm

    def settings(self):
        # Use real settings except for model name
        s = self._inner.settings()
        try:
            s.OLLAMA_MODEL = _FakeSettings().OLLAMA_MODEL  # type: ignore[attr-defined]
        except Exception:
            pass
        return s


def _qa_corpus() -> List[PlannerExample]:
    return [
        PlannerExample("go back", ["back"], category="nav"),
        PlannerExample("reload the page", ["reload"], category="nav"),
        PlannerExample("scroll down a bit", ["scroll"], category="scroll"),
        PlannerExample("download the report", ["download"], category="download"),
        PlannerExample("check that the URL contains /dashboard", ["assertUrl"], category="asserts"),
        PlannerExample("submit the form", ["press"], category="forms"),
        PlannerExample("assert that 'Invalid password' is shown", ["assertText"], category="errors"),
    ]


def _build_app_glue():
    import engine.api.routes.plan as plan_mod  # type: ignore

    def _container_factory():
        return _GlueContainer()

    plan_mod.Container = _container_factory  # type: ignore[attr-defined]
    from engine.api.server import create_app  # type: ignore

    return create_app()


def _build_app_llm():
    # Use default Container/LLM; requires KAIZEN_LLM_ENABLED etc. in environment
    from engine.api.server import create_app  # type: ignore

    return create_app()


def _plan_fn_from_app(app):
    client = TestClient(app)

    def _plan(text: str):
        r = client.post("/api/plan/preview", json={"text": text})
        if r.status_code != 200:
            return []
        data = r.json()
        if not data.get("valid"):
            return []
        plan = data.get("plan") or []
        return [
            step.get("tool")
            for step in plan
            if isinstance(step, dict) and isinstance(step.get("tool"), str)
        ]

    return _plan


def main() -> int:
    corpus = _qa_corpus()

    # Glue evaluation
    glue_app = _build_app_glue()
    glue_plan_fn = _plan_fn_from_app(glue_app)
    glue_metrics = evaluate_examples(corpus, glue_plan_fn)
    print("GLUE:", glue_metrics)

    # LLM evaluation (may fail if LLM not configured; caller's responsibility)
    try:
        llm_app = _build_app_llm()
        llm_plan_fn = _plan_fn_from_app(llm_app)
        llm_metrics = evaluate_examples(corpus, llm_plan_fn)
        print("LLM:", llm_metrics)
    except Exception as e:
        print(f"LLM evaluation skipped due to error: {e!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

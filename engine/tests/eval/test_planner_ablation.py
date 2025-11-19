from __future__ import annotations

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

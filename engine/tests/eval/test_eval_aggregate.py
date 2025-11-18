from engine.eval.harness import aggregate, EvalCase


def test_aggregate_basic():
    c1 = EvalCase(case_id="a", html="<html></html>", step_text="press Enter")
    c2 = EvalCase(case_id="b", html="<html></html>", step_text="press Enter")
    rows = [
        (c1, True, {"duration": 0.1}),
        (c2, False, {"duration": 0.3}),
    ]
    s = aggregate(rows)
    assert s["total"] == 2 and s["passed"] == 1 and s["failed"] == 1
    assert 0.19 <= s["avg_time_seconds"] <= 0.21
    # by_category should group both into generic
    assert "by_category" in s
    gc = s["by_category"]["generic"]
    assert gc["total"] == 2 and gc["passed"] == 1 and gc["failed"] == 1

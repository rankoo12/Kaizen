from __future__ import annotations

from engine.eval.e2e_qa_runs import (
    QAE2ECase,
    default_qa_e2e_cases,
    run_qa_e2e_case,
    run_all_qa_e2e_cases,
)


class _FakeLiveRunner:
    def __init__(self) -> None:
        self.calls = []

    def run_sync(self, spec, *, url: str | None = None) -> str:
        self.calls.append((spec, url))
        # fabricate a run_id based on spec.id to keep it deterministic
        return f"run-{getattr(spec, 'id', 'unknown')}"


def test_default_qa_e2e_cases_structure():
    cases = default_qa_e2e_cases()
    assert len(cases) >= 2
    ids = {c.case_id for c in cases}
    assert "login_success_url_assert" in ids
    assert "login_invalid_password_error" in ids
    cats = {c.category for c in cases}
    assert "forms" in cats and "errors" in cats


def test_run_qa_e2e_case_with_fake_runner():
    runner = _FakeLiveRunner()
    case = QAE2ECase(
        case_id="qa1",
        mode="live",
        url="about:blank",
        steps=["submit the form"],
        category="forms",
    )
    res = run_qa_e2e_case(runner, case)
    assert res["case_id"] == "qa1"
    assert res["run_id"] == "run-qa1"
    assert res["mode"] == "live"
    # Ensure runner was called once with expected URL
    assert len(runner.calls) == 1
    spec, url = runner.calls[0]
    assert getattr(spec, "id") == "qa1"
    assert url == "about:blank"


def test_run_all_qa_e2e_cases_uses_runner_for_each():
    runner = _FakeLiveRunner()
    results = run_all_qa_e2e_cases(runner)
    cases = default_qa_e2e_cases()
    assert len(results) == len(cases)
    assert len(runner.calls) == len(cases)
    # All results should carry case_id and run_id
    for res in results:
        assert "case_id" in res and "run_id" in res

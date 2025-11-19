from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


class ILiveRunner(Protocol):
    def run_sync(self, spec: Any, *, url: str | None = None) -> str: ...


@dataclass
class QAE2ECase:
    case_id: str
    mode: str  # "live" only for now
    url: str
    steps: List[str]
    category: str = "generic"


class _Step:
    def __init__(self, text: str) -> None:
        self.text = text


class _Spec:
    def __init__(self, suite: str, name: str, test_id: str, steps: List[str]) -> None:
        self.suite = suite
        self.name = name
        self.id = test_id
        self.steps = [_Step(s) for s in steps]


def default_qa_e2e_cases() -> List[QAE2ECase]:
    """Small corpus of QA-style flows for live runs.

    These are intentionally simple and deterministic; HTML/URLs are provided by
    the caller (for real runs) and ignored in unit tests that use fake runners.
    """
    return [
        QAE2ECase(
            case_id="login_success_url_assert",
            mode="live",
            url="about:blank",
            steps=[
                "type user@example.com into email field",
                "type correct-password into password field",
                "submit the form",
                "check that the URL contains /dashboard",
            ],
            category="forms",
        ),
        QAE2ECase(
            case_id="login_invalid_password_error",
            mode="live",
            url="about:blank",
            steps=[
                "type user@example.com into email field",
                "type wrong-password into password field",
                "submit the form",
                "assert that 'Invalid password' is shown",
            ],
            category="errors",
        ),
    ]


def run_qa_e2e_case(live_runner: ILiveRunner, case: QAE2ECase) -> Dict[str, Any]:
    """Execute a QA E2E case using the provided live runner.

    Returns a dict with case_id, run_id, and mode for reporting.

    In tests we pass a fake runner; in real usage, Container().live_runner().
    """
    if case.mode != "live":
        raise ValueError(f"unsupported mode: {case.mode}")
    spec = _Spec(suite="qa", name=case.case_id, test_id=case.case_id, steps=case.steps)
    run_id = live_runner.run_sync(spec, url=case.url)
    return {"case_id": case.case_id, "run_id": run_id, "mode": case.mode}


def run_all_qa_e2e_cases(live_runner: ILiveRunner) -> List[Dict[str, Any]]:
    """Run all default QA E2E cases with the given live runner."""
    results: List[Dict[str, Any]] = []
    for case in default_qa_e2e_cases():
        try:
            res = run_qa_e2e_case(live_runner, case)
        except Exception as e:
            res = {"case_id": case.case_id, "run_id": None, "mode": case.mode, "error": str(e)}
        results.append(res)
    return results

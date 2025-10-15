from engine.core.validation.plan_validator import validate_plan, PlanValidationError
import pytest


def test_valid_plan_open_click():
    plan = [
        {"tool": "open", "args": {"url": "https://example.com"}},
        {"tool": "click", "args": {"target": {"text": "Login"}}},
    ]
    validate_plan(plan)  # no exception


def test_invalid_tool_raises():
    bad = [{"tool": "noop", "args": {}}]
    with pytest.raises(PlanValidationError):
        validate_plan(bad)


def test_type_requires_text():
    bad = [{"tool": "type", "args": {"target": {"text": "q"}}}]  # missing "text"
    with pytest.raises(PlanValidationError):
        validate_plan(bad)

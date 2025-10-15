from __future__ import annotations
from jsonschema import Draft202012Validator, exceptions as js_ex
from ..types.schemas import PlanSchema
from typing import Any

_validator = Draft202012Validator(PlanSchema)


class PlanValidationError(ValueError):
    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


def validate_plan(plan: Any) -> None:
    """Raise PlanValidationError if invalid; otherwise return None."""
    errors = sorted(_validator.iter_errors(plan), key=lambda e: e.path)
    if errors:
        msgs = [
            f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        ]
        raise PlanValidationError("Invalid plan", msgs)

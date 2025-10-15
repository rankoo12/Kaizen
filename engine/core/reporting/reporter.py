from typing import Protocol


class StepRun(dict):
    """Serializable step record for reports/artifacts."""

    pass


class IReporter(Protocol):
    """Per-step and on-finish reporting hooks."""

    def on_step(self, step_run: StepRun) -> None: ...
    def on_finish(self, run_id: str) -> None: ...

import pytest


def test_snapshot_runner_integration(container):

    # --- Fake Spec object ---
    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        def __init__(self):
            self.id = "t1"
            self.steps = [Step("Find login button")]

    spec = Spec()

    # --- Mock storage to track calls ---
    calls = {"start": False, "record": 0, "finish": False}
    storage = type(
        "FakeStorage",
        (),
        {
            "start_run": lambda self, test_id: "run-1",
            "record_step": lambda self, step: calls.__setitem__(
                "record", calls["record"] + 1
            ),
            "finish_run": lambda self, run_id: calls.__setitem__("finish", True),
        },
    )()

    # override container storage + resolver for isolation
    container.storage.override(storage)
    container.resolve_snapshot.override(
        lambda **kwargs: {
            "candidates": [{"type": "role", "value": "button[name='Login']"}],
            "reason": "semantic match",
            "dom_path": "/tmp/dom.html",
            "screenshot_path": "/tmp/screen.png",
            "duration_ms": 42,
        }
    )
    runner = container.snapshot_runner()
    run_id = runner.run(spec, html="<html></html>")

    assert run_id.startswith("run-")
    assert calls["record"] == 1
    assert calls["finish"] is True

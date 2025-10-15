import os
import pathlib
import pytest

try:
    import playwright  # noqa: F401
except Exception:
    pytest.skip("Playwright not available", allow_module_level=True)


def test_live_runner_offline_screenshot(container, tmp_path, monkeypatch):
    # run inside a temp dir so the screenshot doesn't touch the repo
    monkeypatch.chdir(tmp_path)

    class Step:
        def __init__(self, text):
            self.text = text

    class Spec:
        def __init__(self):
            self.id = "demo-1"
            self.steps = [Step("noop"), Step("click login")]

    runner = container.live_runner()
    run_id = runner.run_sync(Spec())  # uses offline data: URL by default

    assert run_id.startswith("run-")
    shot = pathlib.Path("demo-1_final.png")
    assert shot.exists() and shot.stat().st_size > 0

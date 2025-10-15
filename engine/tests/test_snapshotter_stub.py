from engine.core.browser.snapshotter import Snapshotter


def test_snapshotter_returns_dict():
    snap = Snapshotter().capture()
    assert "html_path" in snap
    assert isinstance(snap["candidates"], list)

import pytest

try:
    import playwright  # noqa: F401
except Exception:
    pytest.skip("Playwright not available", allow_module_level=True)


def test_live_healing_with_debug_success(container, monkeypatch):
    # Enable healer deterministically
    class _S:
        HEALER_ENABLED = True
        HEALER_PATH = "deterministic"
        ALLOWED_URL_SCHEMES = ["data:", "about:blank"]

    container.settings.override(_S())
    orch = container.orchestrator()

    # data: URL with a button that healer should pick via debug hint
    html = """
    <html><body>
      <button id="go">Go!</button>
    </body></html>
    """
    import urllib.parse as _u

    url = "data:text/html," + _u.quote(html)
    spec = {"id": "heal-debug", "steps": [{"text": "click [heal-success:#go]"}]}

    run_id = orch.run_live(spec, url=url)
    assert run_id.startswith("run-")

    # Fetch rolled up stats from orchestrator reporter
    rep = getattr(orch, "_reporter", None)
    assert rep is not None
    found = next((r for r in (getattr(rep, "_runs", []) or []) if r.get("run_id") == run_id), None)
    assert found is not None
    st = found.get("stats", {})
    assert int(st.get("heal_attempts", 0)) >= 1
    assert int(st.get("heal_successes", 0)) >= 1

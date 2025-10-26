from pathlib import Path
import json
from fastapi.testclient import TestClient
from engine.api.server import create_app
from engine.core.config.settings import settings


def _client():
    app = create_app()
    return TestClient(app)


def test_artifacts_listing_and_fetch(tmp_path):
    client = _client()
    run_id = "art-1"

    # Prepare fake per-run log
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (settings.LOGS_DIR / f"run-{run_id}.jsonl").write_text("{\"msg\": \"hello test\"}\n", encoding="utf-8")

    # Prepare snapshot dir with resolve.json referencing run_id
    snap_dir = settings.SNAPSHOTS_DIR / "suite" / "test"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "resolve.json").write_text(json.dumps({"run_id": run_id, "ok": True}), encoding="utf-8")
    (snap_dir / "steps.jsonl").write_text("{\"s\":1}\n", encoding="utf-8")
    (snap_dir / "input.html").write_text("<html>contact: test@example.com</html>", encoding="utf-8")

    # List artifacts
    res = client.get(f"/api/runs/{run_id}/artifacts")
    assert res.status_code == 200, res.text
    items = res.json().get("items")
    names = {i["name"] for i in items}
    assert {"log", "resolve", "steps", "input"}.issubset(names)

    # Fetch and ensure scrubbing occurred for HTML
    html_res = client.get(f"/api/runs/{run_id}/artifacts/input")
    assert html_res.status_code == 200
    assert "[REDACTED_EMAIL]" in html_res.text

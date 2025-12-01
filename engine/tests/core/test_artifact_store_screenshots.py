from __future__ import annotations

from pathlib import Path

from engine.core.artifacts.store import FSArtifactStore


def test_fs_artifact_store_lists_per_action_screenshots(tmp_path: Path):
    logs = tmp_path / "logs"
    snaps = tmp_path / "snaps"
    logs.mkdir()
    snaps.mkdir()

    run_id = "run-screens"
    # Minimal run log to make the store consider this run_id
    (logs / f"run-{run_id}.jsonl").write_text("{}", encoding="utf-8")
    # Final screenshot
    (logs / f"screenshot-{run_id}.png").write_bytes(b"PNG")
    # Per-action screenshots
    (logs / f"screenshot-{run_id}-a0-before.png").write_bytes(b"PNG0B")
    (logs / f"screenshot-{run_id}-a0-after.png").write_bytes(b"PNG0A")
    (logs / f"screenshot-{run_id}-a1-before.png").write_bytes(b"PNG1B")

    store = FSArtifactStore(logs, snaps)
    names = {item["name"] for item in store.list(run_id)}

    assert "screenshot" in names
    assert "screenshot/a0_before" in names
    assert "screenshot/a0_after" in names
    assert "screenshot/a1_before" in names

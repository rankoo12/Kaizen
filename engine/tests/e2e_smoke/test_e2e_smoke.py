import json
import sys
import subprocess
from pathlib import Path
from urllib.parse import quote


def _repo_root() -> Path:
    # file is at engine/tests/e2e_smoke/test_e2e_smoke.py
    return Path(__file__).resolve().parents[3]


def _data_url_for_html(html_path: Path) -> str:
    content = html_path.read_text(encoding="utf-8")
    return "data:text/html," + quote(content)


def _latest_snapshot_dir(root: Path) -> Path | None:
    """
    Find the newest snapshot artifact folder by resolve.json mtime.
    Returns the parent directory containing resolve.json and steps.jsonl.
    """
    base = root / "snapshots"
    if not base.exists():
        return None
    candidates = []
    for resolve_file in base.rglob("resolve.json"):
        try:
            mtime = resolve_file.stat().st_mtime
            candidates.append((mtime, resolve_file.parent))
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _metrics_path(root: Path) -> Path:
    return (root / "logs" / "metrics.json").resolve()


def _metrics_count(root: Path) -> int:
    p = _metrics_path(root)
    if not p.exists():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("runs_total", 0))
    except Exception:
        return 0


def test_e2e_smoke_snapshot_and_live(tmp_path):
    root = _repo_root()

    # Fixtures & specs
    fixtures_dir = root / "engine" / "tests" / "e2e_smoke" / "fixtures"
    specs_dir = root / "engine" / "tests" / "e2e_smoke" / "specs"

    html_path = fixtures_dir / "smoke.html"
    snapshot_spec = specs_dir / "snapshot_spec.json"
    live_spec = specs_dir / "live_spec.json"

    assert html_path.exists(), "smoke.html is missing"
    assert snapshot_spec.exists(), "snapshot_spec.json is missing"
    assert live_spec.exists(), "live_spec.json is missing"

    # -----------------------
    # Snapshot run (static)
    # -----------------------
    before_snap = _metrics_count(root)
    snap_cmd = [
        sys.executable,
        "-m",
        "engine.api.cli",
        "snapshot-run",
        str(snapshot_spec),
        "--html",
        str(html_path),
    ]
    snap = subprocess.run(snap_cmd, capture_output=True, text=True, cwd=root)
    assert (
        snap.returncode == 0
    ), f"snapshot-run failed:\nSTDOUT:\n{snap.stdout}\nSTDERR:\n{snap.stderr}"
    after_snap = _metrics_count(root)
    assert (
        after_snap >= before_snap + 1
    ), f"metrics not incremented by snapshot run: before={before_snap}, after={after_snap}"

    # Discover the produced artifact directory dynamically
    snapshots_dir = _latest_snapshot_dir(root)
    assert (
        snapshots_dir is not None
    ), "Snapshot artifact directory not found (resolve.json not discovered)"

    steps_file = snapshots_dir / "steps.jsonl"
    resolve_file = snapshots_dir / "resolve.json"

    assert steps_file.exists(), "steps.jsonl not found after snapshot-run"
    assert resolve_file.exists(), "resolve.json not found after snapshot-run"

    # Basic sanity on artifacts
    lines = steps_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1, "steps.jsonl should contain at least one record"
    summary = json.loads(resolve_file.read_text(encoding="utf-8"))
    # Don't rely on suite/test naming here—just ensure structure exists
    assert isinstance(summary.get("steps"), int) and summary["steps"] >= 1
    assert "run_id" in summary

    # -----------------------
    # Live run (browser)
    # -----------------------
    before_live = _metrics_count(root)
    data_url = _data_url_for_html(html_path)
    live_cmd = [
        sys.executable,
        "-m",
        "engine.api.cli",
        "live-run",
        str(live_spec),
        "--url",
        data_url,
    ]
    live = subprocess.run(live_cmd, capture_output=True, text=True, cwd=root)
    assert (
        live.returncode == 0
    ), f"live-run failed:\nSTDOUT:\n{live.stdout}\nSTDERR:\n{live.stderr}"
    after_live = _metrics_count(root)
    assert (
        after_live >= before_live + 1
    ), f"metrics not incremented by live run: before={before_live}, after={after_live}"

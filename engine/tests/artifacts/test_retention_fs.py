from __future__ import annotations

from pathlib import Path
import time

from engine.core.artifacts.store import prune_fs_artifacts


def test_prune_by_age(tmp_path: Path):
    a = tmp_path / "old.log"
    b = tmp_path / "new.log"
    a.write_text("x")
    b.write_text("y")
    old_time = time.time() - 10 * 86400
    # set mtime to old
    import os
    os.utime(a, (old_time, old_time))
    summary = prune_fs_artifacts([tmp_path], max_age_days=7, max_total_bytes=None)
    assert summary["files_deleted"] >= 1
    assert not a.exists() and b.exists()


def test_prune_by_size(tmp_path: Path):
    files = []
    for i in range(5):
        p = tmp_path / f"f{i}.bin"
        data = b"x" * (100 + i * 10)
        p.write_bytes(data)
        files.append(p)
        time.sleep(0.01)
    summary = prune_fs_artifacts([tmp_path], max_age_days=None, max_total_bytes=200)
    assert summary["files_deleted"] >= 1
    remaining = sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())
    assert remaining <= 200

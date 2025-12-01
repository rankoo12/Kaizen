from __future__ import annotations

from typing import Protocol, List, Dict, Tuple
from pathlib import Path
import os
import time


class IArtifactStore(Protocol):
    def list(self, run_id: str) -> List[Dict]: ...
    def get_bytes(
        self, run_id: str, name: str
    ) -> Tuple[bytes, str]: ...  # (data, media_type)


class FSArtifactStore(IArtifactStore):
    def __init__(self, logs_dir: Path, snaps_dir: Path):
        self.logs = logs_dir
        self.snaps = snaps_dir

    def _find_snapshot_dir_for_run(self, run_id: str) -> Path | None:
        if not self.snaps.exists():
            return None
        try:
            for p in self.snaps.rglob("resolve.json"):
                try:
                    import json

                    with p.open("r", encoding="utf-8") as fp:
                        payload = json.load(fp)
                    if str(payload.get("run_id")) == str(run_id):
                        return p.parent
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _artifact_map(self, run_id: str) -> Dict[str, Path]:
        items: Dict[str, Path] = {}
        run_log = self.logs / f"run-{run_id}.jsonl"
        if run_log.exists():
            items["log"] = run_log
        scr = self.logs / f"screenshot-{run_id}.png"
        if scr.exists():
            items["screenshot"] = scr
        # Per-action screenshots: screenshot-<run_id>-a<idx>-before/after.png
        try:
            for p in self.logs.glob(f"screenshot-{run_id}-a*-*.png"):
                if not p.is_file():
                    continue
                name = p.name
                try:
                    # name pattern: screenshot-<run_id>-a{idx}-{phase}.png
                    suffix = name.replace(f"screenshot-{run_id}-a", "", 1)
                    suffix = suffix.rsplit(".png", 1)[0]
                    idx_str, phase = suffix.split("-", 1)
                    artifact_name = f"screenshot/a{idx_str}_{phase}"
                except Exception:
                    continue
                items[artifact_name] = p
        except Exception:
            pass
        # Downloads saved under logs/downloads/<run_id> (flat listing)
        dl_dir = self.logs / "downloads" / str(run_id)
        try:
            if dl_dir.exists():
                for p in dl_dir.rglob("*"):
                    if p.is_file():
                        # Name is prefixed to avoid key collisions
                        items[f"download/{p.name}"] = p
        except Exception:
            pass
        snap_dir = self._find_snapshot_dir_for_run(run_id)
        if snap_dir and snap_dir.exists():
            maybe = {
                "resolve": snap_dir / "resolve.json",
                "steps": snap_dir / "steps.jsonl",
                "input": snap_dir / "input.html",
            }
            for k, p in maybe.items():
                if p.exists():
                    items[k] = p
        return items

    def list(self, run_id: str) -> List[Dict]:
        amap = self._artifact_map(run_id)
        out: List[Dict] = []
        for name, p in amap.items():
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
            out.append({"name": name, "path": str(p), "size": size})
        return out

    def get_bytes(self, run_id: str, name: str) -> Tuple[bytes, str]:
        amap = self._artifact_map(run_id)
        path = amap.get(name)
        if path is None:
            raise FileNotFoundError(name)
        suf = path.suffix.lower()
        if suf in (".jsonl", ".log", ".json", ".html", ".htm"):
            try:
                text = path.read_text(encoding="utf-8")
                # PII scrub (basic)
                import re

                text = re.sub(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                    "[REDACTED_EMAIL]",
                    text,
                )
                text = re.sub(r"\b(?:\d[ -]?){13,16}\b", "[REDACTED_NUMBER]", text)
                return text.encode("utf-8"), "text/plain; charset=utf-8"
            except Exception:
                data = path.read_bytes()
                return data, "application/octet-stream"
        data = path.read_bytes()
        return data, "application/octet-stream"


class MinioArtifactStore(IArtifactStore):
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        secure: bool = True,
    ):
        self._endpoint = endpoint
        self._bucket = bucket
        self._access = access_key
        self._secret = secret_key
        self._secure = bool(secure)

    def _client(self):
        try:
            from minio import Minio  # type: ignore
        except Exception as e:
            raise RuntimeError("minio client not available") from e
        return Minio(
            self._endpoint,
            access_key=self._access,
            secret_key=self._secret,
            secure=self._secure,
        )

    def list(self, run_id: str) -> List[Dict]:
        cli = self._client()
        prefix = f"runs/{run_id}/"
        out: List[Dict] = []
        try:
            for obj in cli.list_objects(self._bucket, prefix=prefix, recursive=True):
                name = obj.object_name.split("/")[-1]
                out.append(
                    {
                        "name": name,
                        "key": obj.object_name,
                        "size": getattr(obj, "size", 0),
                    }
                )
        except Exception:
            pass
        return out

    def get_bytes(self, run_id: str, name: str) -> Tuple[bytes, str]:
        cli = self._client()
        key = f"runs/{run_id}/{name}"
        try:
            resp = cli.get_object(self._bucket, key)
            data = resp.read()
            resp.close()
            resp.release_conn()
            # naive media type detection; caller can override
            mt = "application/octet-stream"
            if name.endswith((".jsonl", ".log", ".json", ".html", ".htm")):
                mt = "text/plain; charset=utf-8"
            return data, mt
        except Exception as e:
            raise FileNotFoundError(name) from e


def get_store_from_settings(settings) -> IArtifactStore:
    try:
        backend = getattr(settings, "ARTIFACTS_BACKEND", "fs")
    except Exception:
        backend = "fs"
    if backend == "minio":
        ep = getattr(settings, "MINIO_ENDPOINT", None)
        bkt = getattr(settings, "MINIO_BUCKET", None)
        ak = getattr(settings, "MINIO_ACCESS_KEY", None)
        sk = getattr(settings, "MINIO_SECRET_KEY", None)
        sec = bool(getattr(settings, "MINIO_SECURE", True))
        if not all([ep, bkt, ak, sk]):
            # Fallback to FS if misconfigured
            return FSArtifactStore(
                Path(getattr(settings, "LOGS_DIR", Path("logs"))),
                Path(getattr(settings, "SNAPSHOTS_DIR", Path("snapshots"))),
            )
        return MinioArtifactStore(ep, bkt, ak, sk, secure=sec)
    # default FS
    return FSArtifactStore(
        Path(getattr(settings, "LOGS_DIR", Path("logs"))),
        Path(getattr(settings, "SNAPSHOTS_DIR", Path("snapshots"))),
    )


def prune_fs_artifacts(
    root_dirs: list[Path],
    max_age_days: int | None = None,
    max_total_bytes: int | None = None,
) -> Dict[str, int]:
    """Delete old artifacts by age and/or total size (oldest first).

    Returns summary dict: {files_deleted, bytes_freed}.
    """
    now = time.time()
    files: list[Tuple[Path, float, int]] = []  # (path, mtime, size)
    for rd in root_dirs:
        try:
            for p in rd.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    files.append((p, st.st_mtime, st.st_size))
        except Exception:
            continue
    files.sort(key=lambda t: t[1])  # oldest first
    deleted = 0
    freed = 0
    # Age pruning
    if isinstance(max_age_days, int) and max_age_days > 0:
        cutoff = now - (max_age_days * 86400)
        for p, mtime, size in list(files):
            if mtime < cutoff:
                try:
                    p.unlink()
                    deleted += 1
                    freed += size
                    files.remove((p, mtime, size))
                except Exception:
                    pass
    # Size pruning
    if isinstance(max_total_bytes, int) and max_total_bytes > 0:
        total = sum(s for _, _, s in files)
        idx = 0
        while total > max_total_bytes and idx < len(files):
            p, _, size = files[idx]
            try:
                p.unlink()
                deleted += 1
                freed += size
                total -= size
            except Exception:
                pass
            idx += 1
    return {"files_deleted": deleted, "bytes_freed": freed}

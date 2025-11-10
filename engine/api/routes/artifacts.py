from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pathlib import Path
from typing import Dict, Any
import json
import re

from engine.core.config.settings import settings
from engine.core.artifacts.store import get_store_from_settings


router = APIRouter(prefix="/api", tags=["artifacts"])


def _scrub_text(data: str) -> str:
    # Basic PII scrubbing: emails and 13-16 digit sequences (credit-card like)
    data = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", data)
    data = re.sub(r"\b(?:\d[ -]?){13,16}\b", "[REDACTED_NUMBER]", data)
    return data


def _find_snapshot_dir_for_run(run_id: str) -> Path | None:
    root = settings.SNAPSHOTS_DIR
    if not root.exists():
        return None
    # Scan for resolve.json that mentions this run_id (bounded)
    try:
        for p in root.rglob("resolve.json"):
            try:
                with p.open("r", encoding="utf-8") as fp:
                    payload = json.load(fp)
                if str(payload.get("run_id")) == str(run_id):
                    return p.parent
            except Exception:
                continue
    except Exception:
        return None
    return None


def _artifact_map(run_id: str) -> Dict[str, Path]:
    items: Dict[str, Path] = {}
    # Per-run JSONL log
    run_log = settings.LOGS_DIR / f"run-{run_id}.jsonl"
    if run_log.exists() and run_log.is_file():
        items["log"] = run_log
    # Final screenshot (live runs via executor)
    scr = settings.LOGS_DIR / f"screenshot-{run_id}.png"
    if scr.exists() and scr.is_file():
        items["screenshot"] = scr
    # Snapshot artifacts (if exist)
    snap_dir = _find_snapshot_dir_for_run(run_id)
    if snap_dir and snap_dir.exists():
        maybe = {
            "resolve": snap_dir / "resolve.json",
            "steps": snap_dir / "steps.jsonl",
            "input": snap_dir / "input.html",
        }
        for k, p in maybe.items():
            if p.exists() and p.is_file():
                items[k] = p
    return items


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str) -> Dict[str, Any]:
    store = get_store_from_settings(settings)
    items = []
    for it in store.list(run_id):
        items.append({
            "name": it.get("name"),
            "size": it.get("size", 0),
            "url": f"/api/runs/{run_id}/artifacts/{it.get('name')}",
        })
    return {"run_id": run_id, "items": items}


def _detect_media_type(path: Path) -> Tuple[str, bool]:
    # Returns (media_type, scrub)
    suf = path.suffix.lower()
    if suf in (".jsonl", ".log"):
        return "text/plain; charset=utf-8", True
    if suf == ".json":
        return "application/json", True
    if suf in (".html", ".htm"):
        return "text/html; charset=utf-8", True
    return "application/octet-stream", False


@router.get("/runs/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str):
    store = get_store_from_settings(settings)
    try:
        data, media_type = store.get_bytes(run_id, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact not found")
    if media_type.startswith("text/"):
        return PlainTextResponse(content=data.decode("utf-8", errors="replace"), media_type=media_type)
    return Response(content=data, media_type=media_type)

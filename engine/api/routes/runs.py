from typing import Any, Dict, List
from pathlib import Path
import json

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

import engine.core.reporting.reporter as reporter_mod
from engine.core.config.settings import settings as _settings


_SEEN_RUN_IDS: set[str] = set()


def register_run_routes(app: FastAPI, orchestrator) -> None:
    """Register minimal run endpoints using the existing orchestrator.

    - POST /api/runs: accepts a payload with a `spec` object and optional
      execution hints; returns a `run_id`.
    - GET /api/runs/{id}: returns run status and minimal stats if finished.
    """

    router = APIRouter(prefix="/api", tags=["runs"])

    def _normalize_action_run(rec: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw action.run log entries into ActionRun-like blocks.

        This keeps the shape close to CONTRACT.md without requiring callers to
        understand the full log schema.
        """
        executor = rec.get("executor") or {}
        exec_status = executor.get("status")
        exec_reason = executor.get("reason")
        selector = executor.get("selector")
        signature = executor.get("signature")
        action_index = rec.get("action_index")
        if not isinstance(action_index, int):
            try:
                action_index = int(rec.get("index"))
            except Exception:
                action_index = None
        out: Dict[str, Any] = {
            "ts": rec.get("ts"),
            "action_index": action_index,
            "tool": rec.get("tool"),
            "semantic_target": rec.get("semantic_target"),
            "ok": bool(rec.get("ok", False)),
            "reason": rec.get("reason"),
            "target_signature": rec.get("target_signature"),
            "pagebrain": rec.get("pagebrain") or {},
            "healer": rec.get("healer") or {},
            # Optional per-action artifacts (e.g. screenshots) when present
            "artifacts": rec.get("artifacts") or {},
        }
        out["executor"] = {
            "status": exec_status,
            # Expose reason as both error and reason for contract-style consumers
            "error": exec_reason,
            "reason": exec_reason,
            "selector": selector,
            "signature": signature,
        }
        return out

    @router.get("/runs")
    async def list_runs(
        request: Request,
        mode: str | None = Query(default=None, description="Filter by mode: live|snapshot"),
        limit: int = Query(default=50, ge=1, le=200),
        since: float | None = Query(default=None, description="Unix epoch seconds; include runs started at or after"),
        offset: int = Query(default=0, ge=0, description="Offset for simple pagination"),
        after: str | None = Query(default=None, description="Cursor: return runs after this run_id"),
    ):
        """List recent runs from reporter; best-effort DB fallback when available.

        - Sorted by started (desc) where available; otherwise preserve insertion order.
        - Mode filter applies to in-memory reporter data.
        - "since" filter compares against reporter "started" timestamps when present, or DB started_at.
        """
        rep = reporter_mod.RUN_REPORTER
        runs: List[dict] = []

        # Prefer in-memory reporter which has richer rollups
        try:
            all_runs = list(getattr(rep, "_runs", []) or [])
            # Include currently running runs from reporter._open so callers
            # can see in-flight executions. These entries will disappear once
            # on_run_finish moves them into _runs.
            try:
                open_runs = list(getattr(rep, "_open", {}).values() or [])
            except Exception:
                open_runs = []
            for cur in open_runs:
                try:
                    rid = cur.get("run_id")
                except Exception:
                    rid = None
                if not rid:
                    continue
                all_runs.append(
                    {
                        "run_id": rid,
                        "mode": cur.get("mode"),
                        "started": cur.get("started"),
                        "stats": {},
                        "by_tool": cur.get("by_tool", {}),
                        "fields": cur.get("fields", {}),
                        "status": "running",
                    }
                )
            # sort desc by started if present
            try:
                all_runs.sort(key=lambda r: float(r.get("started", 0) or 0), reverse=True)
            except Exception:
                pass
            # apply filters
            if mode:
                m = str(mode).lower()
                all_runs = [r for r in all_runs if str(r.get("mode") or "").lower() == m]
            if since is not None:
                try:
                    s = float(since)
                    all_runs = [r for r in all_runs if float(r.get("started", 0) or 0) >= s]
                except Exception:
                    pass
            # Cursor-based pagination: if 'after' provided, find its index and start after it
            if after:
                try:
                    idx = next(i for i, r in enumerate(all_runs) if str(r.get("run_id")) == str(after))
                    start = idx + 1
                except StopIteration:
                    start = 0
                window = all_runs[start : start + limit]
                total = len(all_runs) - start
            else:
                total = len(all_runs)
                window = all_runs[offset : offset + limit]
            runs = []
            for r in window:
                item = {
                    "run_id": r.get("run_id"),
                    "mode": r.get("mode"),
                    "started": r.get("started"),
                    "stats": r.get("stats", {}),
                    "by_tool": r.get("by_tool", {}),
                    "fields": r.get("fields", {}),
                }
                # Optional timing hints captured by the reporter
                if "finished" in r:
                    item["finished"] = r.get("finished")
                if "duration" in r:
                    item["duration"] = r.get("duration")
                if "status" in r:
                    item["status"] = r.get("status")
                runs.append(item)
            return {"runs": runs, "total": total, "offset": offset, "limit": limit}
        except Exception:
            runs = []

        # Fallback: best-effort DB query when reporter not available
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
            if hasattr(st, "_conn"):
                args: list[Any] = []
                sql = (
                    "SELECT run_id, test_id, extract(epoch from started_at) as started, extract(epoch from finished_at) as finished, stats, tenant_id "
                    "FROM runs"
                )
                where = []
                # Tenant filter when multitenancy is enforced and API key resolves
                try:
                    from engine.core.config.settings import settings as _settings
                    if getattr(_settings, "MULTITENANT_ENFORCED", False) and request is not None:
                        resolver = getattr(st, "resolve_tenant", None)
                        tenant_id = resolver(request.headers.get("X-API-Key")) if callable(resolver) else None
                        if tenant_id is None:
                            raise HTTPException(status_code=401, detail="unauthorized")
                        where.append("tenant_id IS NOT DISTINCT FROM %s")
                        args.append(tenant_id)
                except Exception:
                    pass
                if since is not None:
                    where.append("started_at >= to_timestamp(%s)")
                    args.append(float(since))
                if where:
                    sql += " WHERE " + " AND ".join(where)
                if after:
                    # Cursor: fetch runs strictly after the 'after' run's started_at
                    # Resolve 'after' first
                    try:
                        with st._conn() as conn:  # type: ignore[attr-defined]
                            with conn.cursor() as cur:
                                cur.execute("SELECT started_at FROM runs WHERE run_id=%s", (str(after),))
                                row = cur.fetchone()
                                if row and row[0]:
                                    where.append("started_at < %s")
                                    args.append(row[0])
                    except Exception:
                        pass
                    if where:
                        sql = (
                            "SELECT run_id, test_id, extract(epoch from started_at) as started, extract(epoch from finished_at) as finished, stats FROM runs WHERE "
                            + " AND ".join(where)
                            + " ORDER BY started_at DESC LIMIT %s"
                        )
                        args.append(int(limit))
                    else:
                        sql += " ORDER BY started_at DESC LIMIT %s"
                        args.append(int(limit))
                else:
                    sql += " ORDER BY started_at DESC LIMIT %s OFFSET %s"
                    args.extend([int(limit), int(offset)])
                out = []
                with st._conn() as conn:  # type: ignore[attr-defined]
                    with conn.cursor() as cur:
                        cur.execute(sql, tuple(args))
                        for row in cur.fetchall():
                            out.append(
                                {
                                    "run_id": row[0],
                                    "mode": None,
                                    "started": float(row[2]) if row[2] is not None else None,
                                    "stats": row[4] or {},
                                    "by_tool": {},
                                    "fields": {},
                                    "finished": float(row[3]) if row[3] is not None else None,
                                    "duration": (
                                        (float(row[3]) - float(row[2]))
                                        if row[3] is not None and row[2] is not None
                                        else None
                                    ),
                                }
                            )
                return {"runs": out, "total": len(out), "offset": offset, "limit": limit}
        except Exception:
            pass
        return {"runs": [], "total": 0, "offset": offset, "limit": limit}

    @router.post("/runs")
    async def create_run(body: Dict[str, Any]):
        mode = str(body.get("mode") or "snapshot").lower()
        spec = body.get("spec") or {}

        try:
            if mode == "live":
                url = body.get("url")
                run_id = orchestrator.run_live(spec, url=url)
            else:
                run_id = orchestrator.run_snapshot(
                    spec,
                    html_path=body.get("html_path"),
                    html=body.get("html"),
                    snapshot_path=body.get("snapshot") or body.get("snapshot_path"),
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"run error: {e!s}")

        return {"run_id": run_id}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        rep = reporter_mod.RUN_REPORTER

        # Check finished runs first
        try:
            for r in getattr(rep, "_runs", []) or []:
                if str(r.get("run_id")) == str(run_id):
                    return {
                        "run_id": run_id,
                        "status": "finished",
                        "stats": r.get("stats", {}),
                        "mode": r.get("mode"),
                        "started": r.get("started"),
                        "by_tool": r.get("by_tool", {}),
                        "fields": r.get("fields", {}),
                    }
        except Exception:
            pass

        # Then check currently open (running) runs
        try:
            cur = getattr(rep, "_open", {}).get(str(run_id))
            if cur is not None:
                by_tool = {t: dict(rc) for t, rc in (cur.get("by_tool") or {}).items()}
                return {
                    "run_id": run_id,
                    "status": "running",
                    "stats": {},
                    "mode": cur.get("mode"),
                    "started": cur.get("started"),
                    "by_tool": by_tool,
                    "fields": cur.get("fields", {}),
                }
        except Exception:
            pass

        return {"run_id": run_id, "status": "unknown", "stats": {}}

    @router.get("/runs/{run_id}/details")
    async def get_run_details(run_id: str):
        """Return enriched run details plus ActionRun-style timeline.

        This endpoint is intended for portal/contract consumers that need more
        than aggregate stats, but do not want to parse JSONL logs directly.
        """
        base = await get_run(run_id)

        # Best-effort extraction of ActionRun-style entries from per-run logs
        actions: List[Dict[str, Any]] = []
        try:
            log_dir = getattr(_settings, "LOGS_DIR", None)
            if log_dir is not None:
                path = Path(log_dir) / f"run-{run_id}.jsonl"
                if path.exists():
                    with path.open("r", encoding="utf-8") as fp:
                        for line in fp:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            if not isinstance(rec, dict):
                                continue
                            if rec.get("event") != "action.run":
                                continue
                            actions.append(_normalize_action_run(rec))
        except Exception:
            actions = []

        # Best-effort join of human annotations per action (when storage supports it)
        try:
            st = getattr(orchestrator, "_storage", None)  # type: ignore[attr-defined]
        except Exception:
            st = None
        annotations_by_index: Dict[int, Dict[str, Any]] = {}
        try:
            if st is not None and hasattr(st, "get_run_action_annotations"):
                rows = st.get_run_action_annotations(str(run_id))  # type: ignore[attr-defined]
                for ann in rows or []:
                    idx = ann.get("action_index")
                    if isinstance(idx, int) and idx not in annotations_by_index:
                        annotations_by_index[idx] = ann
        except Exception:
            annotations_by_index = {}
        for act in actions:
            idx = act.get("action_index")
            if isinstance(idx, int) and idx in annotations_by_index:
                ann = annotations_by_index[idx]
                act["annotation"] = {
                    "label": ann.get("label"),
                    "source": ann.get("source"),
                    "notes": ann.get("notes"),
                    "user_id": ann.get("user_id"),
                }

        return {"run": base, "actions": actions}

    @router.get("/runs/{run_id}/annotations")
    async def get_run_annotations(run_id: str):
        """Return stored human/ML annotations for a run, when available."""
        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        if st is not None and hasattr(st, "get_run_action_annotations"):
            try:
                rows = st.get_run_action_annotations(str(run_id))  # type: ignore[attr-defined]
                return {"run_id": run_id, "annotations": rows or []}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"annotations error: {e!s}")
        # Fallback when storage does not support annotations
        return {"run_id": run_id, "annotations": []}

    @router.post("/runs/{run_id}/annotations")
    async def add_run_annotation(run_id: str, body: Dict[str, Any]):
        """Create or update an annotation for a specific action within a run.

        Body expects:
          - action_index: int
          - label: "passed" | "failed" (or arbitrary string)
          - source: optional, defaults to "human_truth"
          - notes: optional free-text
          - selector/tool/target_signature/domain: optional, for PageBrain feedback
        """
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="invalid payload")
        action_index = body.get("action_index")
        try:
            action_index = int(action_index)
        except Exception:
            raise HTTPException(status_code=422, detail="action_index must be an integer")
        label = body.get("label")
        if not isinstance(label, str) or not label:
            raise HTTPException(status_code=422, detail="label is required")
        source = body.get("source") or "human_truth"
        notes = body.get("notes")
        if notes is not None and not isinstance(notes, str):
            try:
                notes = str(notes)
            except Exception:
                notes = None
        # Optional extra fields used for PageBrain feedback
        selector = body.get("selector")
        tool = body.get("tool")
        target_signature = body.get("target_signature")
        domain = body.get("domain")

        try:
            st = orchestrator._storage  # type: ignore[attr-defined]
        except Exception:
            st = None
        ann: Dict[str, Any] | None = None
        if st is not None and hasattr(st, "save_run_action_annotation"):
            try:
                ann = st.save_run_action_annotation(  # type: ignore[attr-defined]
                    run_id=str(run_id),
                    action_index=int(action_index),
                    label=str(label),
                    source=str(source),
                    notes=notes,
                    user_id=None,
                    selector=selector if isinstance(selector, dict) else None,
                    domain=str(domain) if isinstance(domain, str) else None,
                    tool=str(tool) if isinstance(tool, str) else None,
                    target_signature=target_signature if isinstance(target_signature, dict) else None,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"annotation error: {e!s}")
        if ann is None:
            # In environments without storage support, echo a minimal annotation
            ann = {
                "run_id": str(run_id),
                "action_index": int(action_index),
                "label": str(label),
                "source": str(source),
                "notes": notes,
            }
        return ann

    @router.post("/runs/{run_id}/finish")
    async def finish_run(run_id: str, body: Dict[str, Any]):
        """Accept final stats from external runner and record in reporter."""
        stats = body.get("stats") or {}
        # guardrail: prevent duplicate run_ids
        if str(run_id) in _SEEN_RUN_IDS:
            raise HTTPException(status_code=409, detail="duplicate run_id")
        try:
            _SEEN_RUN_IDS.add(str(run_id))
            try:
                print(f"[runs] finish: run_id={run_id} stats_keys={list(stats.keys())}")
            except Exception:
                pass
            reporter_mod.RUN_REPORTER.on_run_finish(run_id, dict(stats))
            reporter_mod.RUN_REPORTER.on_finish(run_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"finish error: {e!s}")
        return {"ok": True}

    app.include_router(router)

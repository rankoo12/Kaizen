from __future__ import annotations

from .types import IPlanner, IResolveSnapshot, StepPlan
from engine.core.logging.log import ILog
from pathlib import Path
import json
import time
from typing import Dict, Any, Optional, Iterable

from engine.core.config.settings import settings


def _safe_name(value: str) -> str:
    return (
        "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in value).strip("-")
        or "test"
    )


def _spec_get(spec: Any, key: str, default: Optional[str] = None) -> Optional[str]:
    """Safely read from dict-like or attribute-based spec."""
    if isinstance(spec, dict):
        return spec.get(key, default)
    return getattr(spec, key, default)


def _spec_steps(spec: Any) -> Iterable[Any]:
    if isinstance(spec, dict):
        return spec.get("steps") or []
    return getattr(spec, "steps", []) or []


def _step_text(step: Any) -> str:
    if isinstance(step, dict):
        return step.get("text") or step.get("action") or ""
    return getattr(step, "text", "") or getattr(step, "action", "") or ""


class SnapshotRunner:
    def __init__(
        self, planner: IPlanner, resolve_snapshot: IResolveSnapshot, storage, log: ILog
    ):
        self._planner = planner
        self._resolve_snapshot = resolve_snapshot
        self._storage = storage
        self._log = log

    def _artifact_dir(self, suite: Optional[str], test_name: Optional[str]) -> Path:
        if not suite:
            raise ValueError("suite is required (got None)")
        if not test_name:
            raise ValueError("test_name is required (got None)")
        suite = _safe_name(suite)
        test_name = _safe_name(test_name)
        d = settings.SNAPSHOTS_DIR / suite / test_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run(
        self,
        spec: Dict[str, Any] | Any,
        html_path: Optional[str] = None,
        html: Optional[str] = None,  # inline HTML alias
        snapshot_path: Optional[
            str
        ] = None,  # explicit artifact dir override (from CLI --snapshot)
    ) -> str:
        """
        Runs a snapshot spec against static HTML.

        Persists in artifact directory:
          - steps.jsonl  : one line per executed step
          - resolve.json : final candidate summary

        Returns:
          - run_id (str)
        """
        suite = _spec_get(spec, "suite") or _spec_get(spec, "project") or "default"
        test_name = (
            _spec_get(spec, "name")
            or _spec_get(spec, "id")
            or _spec_get(spec, "title")
            or "run"
        )

        # Choose artifact directory: explicit snapshot_path wins; otherwise default layout.
        if snapshot_path:
            artifact_dir = Path(snapshot_path)
            artifact_dir.mkdir(parents=True, exist_ok=True)
        else:
            artifact_dir = self._artifact_dir(suite, test_name)

        # If inline HTML is provided, persist it and use as html_path
        if html and not html_path:
            inline_html_file = artifact_dir / "input.html"
            inline_html_file.write_text(html, encoding="utf-8")
            html_path = str(inline_html_file)

        # Start run in storage (if implemented) and prefer its run_id
        run_id = None
        if self._storage is not None:
            start = getattr(self._storage, "start_run", None)
            if callable(start):
                try:
                    storage_run_id = start(test_id=test_name)
                    if storage_run_id:
                        run_id = str(storage_run_id)
                except TypeError:
                    storage_run_id = start(test_name)
                    if storage_run_id:
                        run_id = str(storage_run_id)

        # Fallback run_id if storage did not provide one
        if not run_id:
            run_id = f"run-{int(time.time())}-{_safe_name(test_name)}"

        # Per-run JSONL logger (if available)
        run_log = None
        if self._log is not None:
            rl = getattr(self._log, "run_logger", None)
            if callable(rl):
                run_log = self._log.run_logger(run_id=run_id)

        steps_jsonl_fp = (artifact_dir / "steps.jsonl").open("a", encoding="utf-8")

        # Planning/resolve loop
        steps_iter = list(_spec_steps(spec))
        all_candidates = []
        for idx, step in enumerate(steps_iter):
            step_action = _step_text(step)
            plan: StepPlan = self._planner.plan(step_action)

            resolve_result = self._resolve_snapshot(
                plan=plan,
                html_path=html_path,
                tolerance=settings.VISUAL_TOLERANCE,
                healer_depth=settings.HEALER_DEPTH,
            )

            # Persist one JSONL line per step
            record = {
                "ts": time.time(),
                "run_id": run_id,
                "step_index": idx,
                "action": step_action,
                "resolve": resolve_result,
            }
            steps_jsonl_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            steps_jsonl_fp.flush()

            if isinstance(resolve_result, dict) and "candidates" in resolve_result:
                all_candidates.append(resolve_result)

            # Mirror to logger (optional)
            if run_log:
                run_log.info(
                    "snapshot_step",
                    step_index=idx,
                    action=step_action,
                    resolve=resolve_result,
                )

            # Record step to storage (if implemented)
            if self._storage is not None:
                rec = getattr(self._storage, "record_step", None)
                if callable(rec):
                    try:
                        rec(record)
                    except TypeError:
                        rec(step)

        steps_jsonl_fp.close()

        # Write final summary
        summary = {
            "suite": suite,
            "test": test_name,
            "run_id": run_id,
            # Best-effort tenant_id for artifact scoping in FS backend
            "tenant_id": (lambda st: (getattr(st, "get_run", lambda _r: {}) (run_id) or {}).get("tenant_id") if st else None)(self._storage),
            "html_path": html_path,
            "tolerance": settings.VISUAL_TOLERANCE,
            "healer_depth": settings.HEALER_DEPTH,
            "steps": len(steps_iter),
            "results": all_candidates,
        }
        (artifact_dir / "resolve.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Optional: copy/record input HTML if path was provided
        if html_path:
            src = Path(html_path)
            if src.exists():
                dst = artifact_dir / "input.html"
                if str(src.resolve()) != str(dst.resolve()):
                    try:
                        dst.write_text(
                            src.read_text(encoding="utf-8"), encoding="utf-8"
                        )
                    except Exception:
                        pass

        # Finish run in storage (if implemented)
        if self._storage is not None:
            fin = getattr(self._storage, "finish_run", None)
            if callable(fin):
                try:
                    fin(run_id)
                except TypeError:
                    fin(run_id=run_id)

        return run_id

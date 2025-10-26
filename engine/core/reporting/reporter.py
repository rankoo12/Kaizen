from typing import Protocol, Dict, Any, List, Optional
from collections import defaultdict
import time
import json
from pathlib import Path


class StepRun(dict):
    """Serializable step record for reports/artifacts."""

    pass


class IReporter(Protocol):
    """Per-step and on-finish reporting hooks."""

    def on_step(self, step_run: StepRun) -> None: ...
    def on_finish(self, run_id: str) -> None: ...
    def on_run_start(self, run_id: str, mode: str, **fields) -> None: ...
    def on_run_finish(self, run_id: str, stats: dict) -> None: ...


class InMemoryRunReporter(IReporter):
    """In-memory reporter storing per-run stats and step aggregates.

    Not thread-safe for heavy concurrency, but fine for local engine/testing.
    """

    def __init__(self) -> None:
        self._runs: List[dict] = []
        self._open: Dict[str, dict] = {}

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        self._open[run_id] = {
            "run_id": run_id,
            "mode": mode,
            "started": time.time(),
            "by_tool": defaultdict(lambda: defaultdict(int)),  # tool -> reason -> count
            "fields": dict(fields or {}),
        }

    def on_step(self, step_run: StepRun) -> None:
        run_id = step_run.get("run_id")
        tool = step_run.get("tool") or "<none>"
        reason = step_run.get("reason") or "none"
        cur = self._open.get(str(run_id))
        if cur is not None:
            cur["by_tool"][tool][reason] += 1

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        cur = self._open.pop(str(run_id), None)
        payload = {"run_id": run_id, "stats": dict(stats or {})}
        if cur is not None:
            payload["mode"] = cur.get("mode")
            payload["started"] = cur.get("started")
            # convert nested defaultdicts to plain dicts
            by_tool = {t: dict(rc) for t, rc in cur["by_tool"].items()}
            payload["by_tool"] = by_tool
            payload["fields"] = cur.get("fields", {})
        self._runs.append(payload)

    def on_finish(self, run_id: str) -> None:
        pass

    # ---------- Query helpers ----------
    def rollups(self, window: int | None = None) -> Dict[str, Any]:
        runs = self._runs[-window:] if window else list(self._runs)
        total = len(runs)
        reasons: Dict[str, int] = defaultdict(int)
        heal_attempts = 0
        heal_successes = 0
        planner_usage: Dict[str, int] = defaultdict(int)
        planner_fallbacks = 0
        modes: Dict[str, int] = defaultdict(int)
        by_tool: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in runs:
            st = r.get("stats", {})
            for k, v in (st.get("reasons") or {}).items():
                reasons[k] += int(v)
            heal_attempts += int(st.get("heal_attempts", 0) or 0)
            heal_successes += int(st.get("heal_successes", 0) or 0)
            planner = st.get("planner")
            if planner:
                planner_usage[str(planner)] += 1
            planner_fallbacks += int(st.get("planner_fallbacks", 0) or 0)
            modes[str(r.get("mode") or "unknown")] += 1
            for tool, rc in (r.get("by_tool") or {}).items():
                for reason, cnt in (rc or {}).items():
                    by_tool[tool][reason] += int(cnt)
        healed_rate = (heal_successes / heal_attempts) if heal_attempts else 0.0
        # cast nested dicts
        by_tool_out = {t: dict(rc) for t, rc in by_tool.items()}
        return {
            "runs": total,
            "reasons": dict(reasons),
            "heal_attempts": heal_attempts,
            "heal_successes": heal_successes,
            "healed_rate": healed_rate,
            "planner_usage": dict(planner_usage),
            "planner_fallbacks": planner_fallbacks,
            "modes": dict(modes),
            "by_tool": by_tool_out,
        }


# Global reporter store for DI + API route
RUN_REPORTER = InMemoryRunReporter()


class JsonlTailReporter(IReporter):
    """Reporter that appends JSONL events and tails them for rollups.

    Multi-process safe for reads; tailing from last offset. On start, seeks to
    end by default to avoid backfilling unless resync_on_start=True.
    """

    def __init__(self, events_path: Path, resync_on_start: bool = False) -> None:
        self._events_path = Path(events_path)
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        self._runs: List[dict] = []
        self._open: Dict[str, dict] = {}
        self._offset: int = 0
        if resync_on_start and self._events_path.exists():
            self._offset = 0
        elif self._events_path.exists():
            self._offset = self._events_path.stat().st_size

    def _write_event(self, ev: dict) -> None:
        try:
            with self._events_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        ev = {"type": "start", "run_id": run_id, "mode": mode, "ts": time.time(), **(fields or {})}
        self._write_event(ev)
        # mirror to memory
        InMemoryRunReporter.on_run_start(self, run_id, mode, **fields)

    def on_step(self, step_run: StepRun) -> None:
        ev = {"type": "step", **dict(step_run)}
        self._write_event(ev)
        InMemoryRunReporter.on_step(self, step_run)

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        ev = {"type": "finish", "run_id": run_id, "ts": time.time(), "stats": dict(stats or {})}
        self._write_event(ev)
        InMemoryRunReporter.on_run_finish(self, run_id, stats)

    def on_finish(self, run_id: str) -> None:
        pass

    def _process_event(self, ev: dict) -> None:
        # Update in-memory only; do not write while tailing
        t = ev.get("type")
        if t == "start":
            InMemoryRunReporter.on_run_start(self, ev.get("run_id", ""), ev.get("mode", "unknown"))
        elif t == "step":
            InMemoryRunReporter.on_step(self, StepRun(ev))
        elif t == "finish":
            InMemoryRunReporter.on_run_finish(self, ev.get("run_id", ""), ev.get("stats", {}))

    def rollups(self, window: int | None = None) -> Dict[str, Any]:
        # ingest new events from file
        try:
            if self._events_path.exists():
                size = self._events_path.stat().st_size
                if size > self._offset:
                    with self._events_path.open("r", encoding="utf-8") as fp:
                        fp.seek(self._offset)
                        for line in fp:
                            try:
                                ev = json.loads(line)
                                # Update in-memory store using base class helpers
                                self._process_event(ev)
                            except Exception:
                                continue
                    self._offset = size
        except Exception:
            pass
        return InMemoryRunReporter.rollups(self, window)

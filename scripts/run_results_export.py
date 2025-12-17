"""
Export contract-style run results (Run + ActionRun timeline) from JSONL logs.

Reads run-*.jsonl logs emitted by RunJsonlLogger and produces:
  - reports/run_results.jsonl

Each line is a JSON object:
  {
    "run_id": "...",
    "status": "passed" | "failed" | "unknown",
    "actions": [ /* normalized ActionRun-like entries */ ]
  }

Action entries are derived from `action.run` events and include:
  - ts, action_index, tool, semantic_target, ok, reason,
  - target_signature, executor, pagebrain, healer
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"


def _iter_action_events() -> Tuple[str, Dict[str, Any]]:
    for path in LOGS.glob("run-*.jsonl"):
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
                yield path.name, rec


def _normalize_action(rec: Dict[str, Any]) -> Dict[str, Any]:
    executor = rec.get("executor") or {}
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
        "ok": bool(rec.get("ok", False)) or bool(executor.get("status") == "passed"),
        "reason": rec.get("reason"),
        "target_signature": rec.get("target_signature") or executor.get("signature"),
        "pagebrain": rec.get("pagebrain") or {},
        "healer": rec.get("healer") or {},
        "perception": rec.get("perception") or {},
    }
    out["executor"] = {
        "status": executor.get("status"),
        "error": executor.get("reason"),
        "reason": executor.get("reason"),
        "selector": executor.get("selector"),
        "signature": executor.get("signature"),
    }
    return out


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / "run_results.jsonl"

    runs: Dict[str, Dict[str, Any]] = {}
    for fname, rec in _iter_action_events():
        run_id = rec.get("run_id") or fname.replace("run-", "").replace(".jsonl", "")
        actions = runs.setdefault(run_id, {}).setdefault("actions", [])
        actions.append(_normalize_action(rec))

    # Normalize status per run based on actions
    for run_id, data in runs.items():
        actions = data.get("actions") or []
        status = "unknown"
        if actions:
            if any(a.get("ok") is False or (a.get("executor") or {}).get("status") == "failed" for a in actions):
                status = "failed"
            elif any(a.get("ok") for a in actions):
                status = "passed"
        data["run_id"] = run_id
        data["status"] = status

    total = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for run_id, data in runs.items():
            fp.write(json.dumps(data, ensure_ascii=False) + "\n")
            total += 1
    print(f"wrote {total} run results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

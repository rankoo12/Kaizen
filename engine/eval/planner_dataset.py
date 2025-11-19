from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List
import json


def build_dataset_from_traces(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert planner.step log records into a simple QA dataset.

    Each example contains:
      - id: run_id-step_index
      - text: original QA step text
      - planner_path: "glue" or "llm"
      - tool_names: list of tool names in order
      - tools: raw tool call dicts (subset of the plan)
    """
    examples: List[Dict[str, Any]] = []
    for rec in records:
        try:
            if rec.get("event") != "planner.step":
                continue
            text = rec.get("text")
            tools = rec.get("tools") or []
            if not isinstance(text, str) or not tools:
                continue
            run_id = rec.get("run_id") or "run"
            step_index = int(rec.get("step_index", 0) or 0)
            planner_path = str(rec.get("planner_path") or "unknown")
            tool_names = [
                t.get("tool")
                for t in tools
                if isinstance(t, dict) and isinstance(t.get("tool"), str)
            ]
            if not tool_names:
                continue
            ex_id = f"{run_id}-{step_index}"
            examples.append(
                {
                    "id": ex_id,
                    "text": text,
                    "planner_path": planner_path,
                    "tool_names": tool_names,
                    "tools": tools,
                }
            )
        except Exception:
            continue
    return examples


def load_traces_from_logs(logs_dir: Path) -> List[Dict[str, Any]]:
    """Best-effort loader for planner.step records from run-*.jsonl logs."""
    records: List[Dict[str, Any]] = []
    for path in logs_dir.glob("run-*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as fp:
                for line in fp:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict) and rec.get("event") == "planner.step":
                        records.append(rec)
        except Exception:
            continue
    return records

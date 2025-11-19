from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import json


def build_dataset_from_traces(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert planner.step log records into a simple QA dataset.

    Each raw example contains:
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


def _normalize_text(text: str) -> str:
    # Collapse whitespace; leave case as-is (case can matter for labels/text)
    return " ".join((text or "").split()).strip()


def _infer_category(text: str, tool_names: List[str]) -> str:
    lower = text.lower()
    tools = set(tool_names)
    if any(t in tools for t in {"assertUrl", "assertText"}):
        return "asserts"
    if "invalid password" in lower or "error" in lower:
        return "errors"
    if "download" in lower:
        return "downloads"
    if "scroll" in lower:
        return "scroll"
    if any(k in lower for k in ["back", "forward", "tab", "window"]):
        return "nav"
    if any(k in lower for k in ["submit", "form", "login", "type "]):
        return "forms"
    return "generic"


def curate_examples(examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter, normalize, categorize, and deduplicate planner examples.

    Returns examples of the form:
      - id, text (normalized), planner_path, category, tool_names, tools
    """
    seen: set[Tuple[str, Tuple[str, ...]]] = set()
    curated: List[Dict[str, Any]] = []
    for ex in examples:
        try:
            text = ex.get("text")
            tool_names = ex.get("tool_names") or []
            tools = ex.get("tools") or []
            if not isinstance(text, str) or not tool_names or not tools:
                continue
            norm_text = _normalize_text(text)
            if not norm_text:
                continue
            key = (norm_text, tuple(tool_names))
            if key in seen:
                continue
            seen.add(key)
            category = _infer_category(norm_text, list(tool_names))
            curated.append(
                {
                    "id": ex.get("id"),
                    "text": norm_text,
                    "planner_path": ex.get("planner_path"),
                    "category": category,
                    "tool_names": list(tool_names),
                    "tools": tools,
                }
            )
        except Exception:
            continue
    return curated


def split_train_dev(examples: List[Dict[str, Any]], dev_every: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Deterministically split examples into train/dev sets.

    Uses a simple stride (every Nth example to dev) over examples sorted by id.
    """
    if not examples:
        return [], []
    sorted_examples = sorted(examples, key=lambda e: str(e.get("id") or ""))
    train: List[Dict[str, Any]] = []
    dev: List[Dict[str, Any]] = []
    for idx, ex in enumerate(sorted_examples):
        if dev_every > 0 and idx % dev_every == 0:
            dev.append(ex)
        else:
            train.append(ex)
    return train, dev


def build_training_examples(examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert curated planner examples into training-ready examples.

    Output schema (per line in JSONL):
      - id: original example id (if present)
      - input: QA step text (normalized)
      - output: JSON string of the tools array (e.g., '[{...}]')
      - category: inferred category (forms/nav/asserts/errors/downloads/scroll/generic)
    """
    out: List[Dict[str, Any]] = []
    for ex in examples:
        try:
            text = ex.get("text")
            tools = ex.get("tools") or []
            if not isinstance(text, str) or not tools:
                continue
            # For training, we serialize tools as a compact JSON string
            output = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
            out.append(
                {
                    "id": ex.get("id"),
                    "input": text,
                    "output": output,
                    "category": ex.get("category") or "generic",
                }
            )
        except Exception:
            continue
    return out

"""
Export planner QA dataset from run JSONL logs.

Usage (from repo root):
  python scripts/planner_export_qa_dataset.py

This reads logs/run-*.jsonl, extracts planner.step events, and writes:
  reports/planner_qa_dataset.jsonl
"""
from __future__ import annotations

from pathlib import Path
import json

from engine.eval.planner_dataset import load_traces_from_logs, build_dataset_from_traces


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs_dir = root / "logs"
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    records = load_traces_from_logs(logs_dir)
    examples = build_dataset_from_traces(records)

    out_path = reports_dir / "planner_qa_dataset.jsonl"
    with out_path.open("w", encoding="utf-8") as fp:
        for ex in examples:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"wrote {len(examples)} examples to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

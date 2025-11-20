"""
End-to-end offline planner QA training loop helper.

This is a thin, deterministic wrapper around the existing dataset/export
functions. It:

- Reads planner.step traces from logs/run-*.jsonl
- Builds a raw QA dataset (text + tools)
- Curates + splits into train/dev
- Produces training-ready JSONL files for external fine-tuning

Usage (from repo root):
  python scripts/planner_offline_training_loop.py

Outputs under reports/:
  - planner_qa_dataset.jsonl
  - planner_qa_train.jsonl
  - planner_qa_dev.jsonl
  - planner_qa_train_export.jsonl
  - planner_qa_dev_export.jsonl

These exports are intended to be consumed by your own LLM training stack
(for example, fine-tuning a small model on the planner QA corpus). To
evaluate a tuned model, point the engine at it (via settings/ENV) and run
scripts/eval_planner_ablation.py to compare against the glue baseline.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.eval.planner_dataset import (  # type: ignore
    build_dataset_from_traces,
    build_training_examples,
    curate_examples,
    load_traces_from_logs,
    split_train_dev,
)


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for ex in rows:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main() -> int:
    logs_dir = ROOT / "logs"
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1) Load planner.step records from run-*.jsonl
    records = load_traces_from_logs(logs_dir)
    examples = build_dataset_from_traces(records)
    dataset_path = reports_dir / "planner_qa_dataset.jsonl"
    _write_jsonl(dataset_path, examples)

    # 2) Curate and split into train/dev
    curated = curate_examples(examples)
    train, dev = split_train_dev(curated, dev_every=5)
    train_path = reports_dir / "planner_qa_train.jsonl"
    dev_path = reports_dir / "planner_qa_dev.jsonl"
    _write_jsonl(train_path, train)
    _write_jsonl(dev_path, dev)

    # 3) Build training-ready JSONL (input/output/category)
    train_export = build_training_examples(train)
    dev_export = build_training_examples(dev)
    train_export_path = reports_dir / "planner_qa_train_export.jsonl"
    dev_export_path = reports_dir / "planner_qa_dev_export.jsonl"
    _write_jsonl(train_export_path, train_export)
    _write_jsonl(dev_export_path, dev_export)

    print(
        "planner_offline_training_loop: "
        f"records={len(records)} examples={len(examples)} curated={len(curated)} "
        f"train={len(train)} dev={len(dev)} "
        f"train_export={len(train_export)} dev_export={len(dev_export)}"
    )
    print("dataset:", dataset_path)
    print("curated train/dev:", train_path, dev_path)
    print("training exports:", train_export_path, dev_export_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Build training-ready planner QA datasets from curated JSONL.

Usage (from repo root, after running planner_curate_qa_dataset.py):
  python scripts/planner_build_training_sets.py

Reads:
  reports/planner_qa_train.jsonl
  reports/planner_qa_dev.jsonl
Writes:
  reports/planner_qa_train_export.jsonl
  reports/planner_qa_dev_export.jsonl
"""
from __future__ import annotations

from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.eval.planner_dataset import build_training_examples  # type: ignore


def _load_curated(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as fp:
        for ex in rows:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main() -> int:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    train_src = reports_dir / "planner_qa_train.jsonl"
    dev_src = reports_dir / "planner_qa_dev.jsonl"

    train_raw = _load_curated(train_src)
    dev_raw = _load_curated(dev_src)

    train_export = build_training_examples(train_raw)
    dev_export = build_training_examples(dev_raw)

    train_out = reports_dir / "planner_qa_train_export.jsonl"
    dev_out = reports_dir / "planner_qa_dev_export.jsonl"
    _write_jsonl(train_out, train_export)
    _write_jsonl(dev_out, dev_export)

    print(
        f"train_export={len(train_export)} dev_export={len(dev_export)} "
        f"-> {train_out} / {dev_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

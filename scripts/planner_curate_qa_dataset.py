"""
Curate planner QA dataset into train/dev splits.

Usage (from repo root, after running planner_export_qa_dataset.py):
  python scripts/planner_curate_qa_dataset.py

Reads:
  reports/planner_qa_dataset.jsonl
Writes:
  reports/planner_qa_train.jsonl
  reports/planner_qa_dev.jsonl
"""
from __future__ import annotations

from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.eval.planner_dataset import curate_examples, split_train_dev  # type: ignore


def _load_raw_examples(path: Path):
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


def main() -> int:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    src = reports_dir / "planner_qa_dataset.jsonl"
    raw = _load_raw_examples(src)
    curated = curate_examples(raw)
    train, dev = split_train_dev(curated, dev_every=5)

    train_path = reports_dir / "planner_qa_train.jsonl"
    dev_path = reports_dir / "planner_qa_dev.jsonl"

    with train_path.open("w", encoding="utf-8") as fp:
        for ex in train:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with dev_path.open("w", encoding="utf-8") as fp:
        for ex in dev:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(
        f"curated={len(curated)} train={len(train)} dev={len(dev)} "
        f"-> {train_path} / {dev_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

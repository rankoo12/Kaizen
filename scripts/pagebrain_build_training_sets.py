"""
Build training-ready PageBrain JSONL exports from curated datasets.

Reads:
  reports/pagebrain_train.jsonl
  reports/pagebrain_dev.jsonl

Writes:
  reports/pagebrain_train_export.jsonl
  reports/pagebrain_dev_export.jsonl

Schema per line:
  - example_id
  - run_id
  - tool
  - semantic_target (optional)
  - executor: {status, reason, selector{type,value}, signature}
  - pagebrain: {chosen, candidates, candidate_count, path, reason}
  - healer: { ... } (optional)
"""

from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def _load(path: Path):
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


def _write(path: Path, rows):
    with path.open("w", encoding="utf-8") as fp:
        for ex in rows:
            fp.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    train_src = REPORTS / "pagebrain_train.jsonl"
    dev_src = REPORTS / "pagebrain_dev.jsonl"

    train = _load(train_src)
    dev = _load(dev_src)

    train_out = REPORTS / "pagebrain_train_export.jsonl"
    dev_out = REPORTS / "pagebrain_dev_export.jsonl"
    _write(train_out, train)
    _write(dev_out, dev)

    print(
        f"train_export={len(train)} dev_export={len(dev)} -> {train_out} / {dev_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

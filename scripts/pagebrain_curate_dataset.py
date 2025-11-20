"""
Curate PageBrain dataset into train/dev splits with success gating.

Reads:
  reports/pagebrain_dataset.jsonl (from scripts/pagebrain_export_dataset.py)

Writes:
  reports/pagebrain_train.jsonl
  reports/pagebrain_dev.jsonl

Rules:
- keep examples where ok is True and pagebrain.chosen selector exists
- simple dev split: every 5th example goes to dev
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
    src = REPORTS / "pagebrain_dataset.jsonl"
    raw = _load(src)
    curated = []
    for ex in raw:
        if not ex.get("ok"):
            continue
        pb = ex.get("pagebrain") or {}
        chosen = pb.get("chosen") if isinstance(pb, dict) else None
        if not (isinstance(chosen, dict)):
            continue
        sel = chosen.get("selector") if isinstance(chosen, dict) else None
        if not (isinstance(sel, dict) and sel.get("type") and sel.get("value")):
            continue
        curated.append(ex)

    train = []
    dev = []
    for idx, ex in enumerate(curated):
        if idx % 5 == 0:
            dev.append(ex)
        else:
            train.append(ex)

    train_out = REPORTS / "pagebrain_train.jsonl"
    dev_out = REPORTS / "pagebrain_dev.jsonl"
    _write(train_out, train)
    _write(dev_out, dev)

    print(
        f"curated={len(curated)} train={len(train)} dev={len(dev)} "
        f"-> {train_out} / {dev_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

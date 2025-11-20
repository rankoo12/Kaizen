"""
Export PageBrain choice events into a raw dataset JSONL.

Reads run-*.jsonl logs that contain `pagebrain.choice` events emitted by the
executor (heuristic PageBrain v1). Produces:

- reports/pagebrain_dataset.jsonl

Each line includes:
  - example_id (derived from run_id + index)
  - run_id
  - tool
  - ok / reason
  - target_signature (if present)
  - pagebrain {chosen, candidates, candidate_count, path, reason}

This is a raw export; a future curation step can split train/dev and apply
success-signal gating.
"""

from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"


def _iter_pagebrain_events():
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
                if rec.get("event") != "pagebrain.choice":
                    continue
                yield path.name, rec


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / "pagebrain_dataset.jsonl"
    total = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for fname, rec in _iter_pagebrain_events():
            run_id = rec.get("run_id") or fname.replace("run-", "").replace(".jsonl", "")
            tool = rec.get("tool")
            pb = rec.get("pagebrain") or {}
            example = {
                "example_id": f"{run_id}-{total}",
                "run_id": run_id,
                "tool": tool,
                "ok": bool(rec.get("ok", False)),
                "reason": rec.get("reason"),
                "target_signature": rec.get("target_signature"),
                "pagebrain": pb,
            }
            fp.write(json.dumps(example, ensure_ascii=False) + "\n")
            total += 1
    print(f"wrote {total} pagebrain examples to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

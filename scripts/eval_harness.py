"""
Evaluation harness for P2/15 (offline snapshot phase).

Runs a small, deterministic corpus of snapshot cases against the ElementResolver
and writes summary reports under reports/:
  - reports/eval-summary.json     (overall + per-category metrics)
  - reports/eval-summary.csv      (one row per case)

Usage (from repo root):
  python scripts/eval_harness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.eval.harness import default_corpus, run_snapshot_case, aggregate, write_reports


def main() -> int:
    corpus = default_corpus()
    rows = []
    for c in corpus:
        ok, meta = run_snapshot_case(c)
        rows.append((c, ok, meta))
    summary = aggregate(rows)
    write_reports(summary, rows)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

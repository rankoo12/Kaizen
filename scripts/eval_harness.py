"""
Evaluation harness (seed) for P2/15.

Runs a small corpus of snapshot cases and writes summary reports:
  - reports/eval-summary.json
  - reports/eval-summary.csv

Usage:
  python scripts/eval_harness.py
"""
from __future__ import annotations

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

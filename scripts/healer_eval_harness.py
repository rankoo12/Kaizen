"""
Offline evaluation harness for DeterministicHealer.

Runs the default healer evaluation corpus and writes summary reports under
reports/:
  - reports/healer_eval_summary.json
  - reports/healer_eval_summary.csv

Usage (from repo root):
  python scripts/healer_eval_harness.py
"""
from __future__ import annotations

from pathlib import Path

from engine.core.healing.selector_healer import DeterministicHealer
from engine.eval.healer_retrieval import run_corpus, write_reports

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    healer = DeterministicHealer(storage=None)
    summary, results = run_corpus(healer)
    write_reports(summary, results)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

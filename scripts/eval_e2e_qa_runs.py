"""
Evaluation harness for end-to-end QA runs (P2).

Uses the live runner to execute a small corpus of QA-style flows and prints
the resulting run_ids. Intended for manual use when the environment has
Playwright/browsers configured.

Usage (from repo root):
  python scripts/eval_e2e_qa_runs.py
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.core.config.container import build_container  # type: ignore
from engine.eval.e2e_qa_runs import run_all_qa_e2e_cases  # type: ignore


def main() -> int:
    container = build_container()
    live_runner = container.live_runner()
    results = run_all_qa_e2e_cases(live_runner)
    for res in results:
        print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

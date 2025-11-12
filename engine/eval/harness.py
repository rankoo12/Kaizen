from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import time

from engine.core.orchestrator.types import StepPlan
from engine.core.resolving.snapshot_resolver import resolve_snapshot as _resolve_snapshot


@dataclass
class EvalCase:
    case_id: str
    html: str
    step_text: str  # e.g., "click Login" or "press Enter"
    expect_tag: str | None = None  # e.g., "button", used for click targets


def _build_plan_from_text(text: str) -> List[Dict[str, Any]]:
    t = (text or "").strip()
    lower = t.lower()
    if lower.startswith("click "):
        raw = t.split(" ", 1)[1].strip()
        return [{"tool": "click", "args": {"target": {"text": raw}}}]
    if lower.startswith("type "):
        typed = t.split(" ", 1)[1].strip()
        return [{"tool": "type", "args": {"target": {"text": "input"}, "text": typed}}]
    if lower.startswith("press "):
        key = t.split(" ", 1)[1].strip()
        return [{"tool": "press", "args": {"key": key}}]
    # default conservative click
    return [{"tool": "click", "args": {"target": {"text": t}}}]


def run_snapshot_case(case: EvalCase) -> Tuple[bool, Dict[str, Any]]:
    # Evaluate using snapshot resolver only (no browser). Success = we got a primary.
    steps = _build_plan_from_text(case.step_text)
    plan = [
        {
            "tool": steps[0]["tool"],
            "args": steps[0].get("args", {}),
        }
    ]
    sp = StepPlan(target_query=plan[0]["args"].get("target", {}))
    # Persist inline HTML to a temp file under reports to leverage snapshot resolver path
    tmp_dir = Path("reports/eval_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    html_path = tmp_dir / f"{case.case_id}.html"
    html_path.write_text(case.html, encoding="utf-8")

    t0 = time.time()
    resolved = _resolve_snapshot(plan=sp, html_path=str(html_path), tolerance=0.0, healer_depth=0)
    dt = time.time() - t0
    primary = resolved.get("primary")
    ok = isinstance(primary, dict)
    if ok and case.expect_tag:
        ok = str(primary.get("type") or "css") in ("css", "id", "testid", "text")
    return ok, {"duration": dt, "resolved": resolved}


def aggregate(results: List[Tuple[EvalCase, bool, Dict[str, Any]]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    durations = [meta.get("duration", 0.0) for _, _, meta in results]
    avg_ttr = (sum(durations) / total) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": (passed / total) if total else 0.0,
        "avg_time_seconds": avg_ttr,
    }


def write_reports(summary: Dict[str, Any], rows: List[Tuple[EvalCase, bool, Dict[str, Any]]]) -> None:
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # Minimal CSV
    lines = ["case_id,ok,duration_s"]
    for case, ok, meta in rows:
        lines.append(f"{case.case_id},{int(bool(ok))},{meta.get('duration', 0.0):.4f}")
    (out_dir / "eval-summary.csv").write_text("\n".join(lines), encoding="utf-8")


def default_corpus() -> List[EvalCase]:
    return [
        EvalCase(
            case_id="btn_login_v1",
            html="""
            <html><body>
              <button id="login">Login</button>
            </body></html>
            """,
            step_text="click Login",
            expect_tag="button",
        ),
        EvalCase(
            case_id="btn_login_v2_drift",
            html="""
            <html><body>
              <button class="primary">Sign in</button>
            </body></html>
            """,
            step_text="click sign in",
            expect_tag="button",
        ),
        EvalCase(
            case_id="press_enter",
            html="<html><body><h1>Press</h1></body></html>",
            step_text="press Enter",
        ),
    ]

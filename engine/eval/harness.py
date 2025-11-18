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
    expect_tag: str | None = None  # reserved for future use
    category: str = "generic"  # e.g., "controls", "dialogs", "lists", "drift"


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

    by_cat: Dict[str, Dict[str, Any]] = {}
    for case, ok, meta in results:
        cat = getattr(case, "category", "generic") or "generic"
        bucket = by_cat.setdefault(cat, {"total": 0, "passed": 0, "failed": 0, "avg_time_seconds": 0.0})
        bucket["total"] += 1
        if ok:
            bucket["passed"] += 1
        bucket["failed"] = bucket["total"] - bucket["passed"]
    for cat, bucket in by_cat.items():
        if bucket["total"]:
            bucket["success_rate"] = bucket["passed"] / bucket["total"]
        else:
            bucket["success_rate"] = 0.0

    summary: Dict[str, Any] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": (passed / total) if total else 0.0,
        "avg_time_seconds": avg_ttr,
    }
    if by_cat:
        summary["by_category"] = by_cat
    return summary


def write_reports(summary: Dict[str, Any], rows: List[Tuple[EvalCase, bool, Dict[str, Any]]]) -> None:
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # Minimal CSV (one row per case)
    lines = ["case_id,category,ok,duration_s"]
    for case, ok, meta in rows:
        cat = getattr(case, "category", "generic") or "generic"
        lines.append(f"{case.case_id},{cat},{int(bool(ok))},{meta.get('duration', 0.0):.4f}")
    (out_dir / "eval-summary.csv").write_text("\n".join(lines), encoding="utf-8")


def default_corpus() -> List[EvalCase]:
    return [
        # --- Controls: simple buttons and inputs ---
        EvalCase(
            case_id="btn_login_v1",
            category="controls",
            html="""
            <html><body>
              <button id="login">Login</button>
            </body></html>
            """,
            step_text="click Login",
        ),
        EvalCase(
            case_id="btn_login_v2_drift_text",
            category="controls_drift",
            html="""
            <html><body>
              <div class="hero">
                <button class="primary">Sign in</button>
              </div>
            </body></html>
            """,
            step_text="click Sign in",
        ),
        EvalCase(
            case_id="btn_ok_cancel_dialog",
            category="dialogs",
            html="""
            <html><body>
              <div role="dialog" aria-label="Confirm">
                <button>Cancel</button>
                <button id="ok">OK</button>
              </div>
            </body></html>
            """,
            step_text="click OK",
        ),
        EvalCase(
            case_id="input_email_labelled",
            category="controls",
            html="""
            <html><body>
              <label for="email">Email</label>
              <input id="email" name="email" type="email" />
            </body></html>
            """,
            step_text="type user@example.com",
        ),
        EvalCase(
            case_id="input_username_placeholder",
            category="controls",
            html="""
            <html><body>
              <input id="user" name="username" placeholder="Username" />
            </body></html>
            """,
            step_text="type my-user",
        ),
        # --- Lists and repeated items ---
        EvalCase(
            case_id="nav_list_items",
            category="lists",
            html="""
            <html><body>
              <a href="/one">Item 1</a>
              <a href="/two">Item 2</a>
            </body></html>
            """,
            step_text="click Item 2",
        ),
        EvalCase(
            case_id="nav_sidebar_links",
            category="lists",
            html="""
            <html><body>
              <nav>
                <a href="/dashboard">Dashboard</a>
                <a href="/settings">Settings</a>
              </nav>
            </body></html>
            """,
            step_text="click Settings",
        ),
        # --- Slight drift in structure but same intent ---
        EvalCase(
            case_id="btn_login_with_icon",
            category="controls_drift",
            html="""
            <html><body>
              <button class="primary">
                <span class="icon">*</span>
                <span>Login</span>
              </button>
            </body></html>
            """,
            step_text="click Login",
        ),
        # --- Simple keyboard shortcut case ---
        EvalCase(
            case_id="press_enter",
            category="shortcuts",
            html="<html><body><h1>Press</h1></body></html>",
            step_text="press Enter",
        ),
        # --- Form-style scenario ---
        EvalCase(
            case_id="form_login_basic",
            category="forms",
            html="""
            <html><body>
              <form>
                <label for="email2">Email</label>
                <input id="email2" name="email" type="email" />
                <label for="pwd">Password</label>
                <input id="pwd" name="password" type="password" />
                <button type="submit">Log in</button>
              </form>
            </body></html>
            """,
            step_text="click Log in",
        ),
    ]

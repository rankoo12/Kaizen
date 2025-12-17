from __future__ import annotations

import json
from pathlib import Path

from engine.core.commands.action_handler import IActionHandler, StepResult, ExecCtx
from engine.core.logging.log import RunJsonlLogger
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.perception import PerceptionLayer


class OkHandler(IActionHandler):
    def execute(self, tool_call, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True)


class SimpleResolver:
    def find(self, target: dict):
        # Minimal live resolver: always returns a single visible/enabled candidate
        return [{"type": "css", "value": "#login", "visible": True, "enabled": True}]


def test_action_run_includes_perception_block(tmp_path: Path):
    logger = RunJsonlLogger(run_id="run-perception", logs_dir=tmp_path)
    handlers = {"click": OkHandler()}
    resolver = SimpleResolver()
    execu = DeterministicPlanExecutor(
        log=logger,
        handlers=handlers,
        resolver=resolver,
        settings=None,
        perception_layer=PerceptionLayer(),
    )
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]

    res = execu.execute(plan, ctx=ExecCtx(run_id="run-perception"))
    assert res and res[0].ok

    log_path = tmp_path / "run-run-perception.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()

    action_events = [json.loads(l) for l in lines if '"action.run"' in l]
    assert action_events, "action.run event not logged"
    ev = action_events[0]
    assert ev["run_id"] == "run-perception"
    # Perception block should always be present when PerceptionLayer is wired
    perception = ev.get("perception")
    assert perception is not None
    diff = (perception or {}).get("screenshot_diff") or {}
    # All expected keys should exist even when screenshots are unavailable
    assert "element_region_diff" in diff
    assert "main_region_diff" in diff
    assert "full_page_diff" in diff

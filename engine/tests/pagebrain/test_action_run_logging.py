from __future__ import annotations

import json
from pathlib import Path

from engine.core.commands.action_handler import IActionHandler, StepResult, ExecCtx
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.logging.log import RunJsonlLogger


class FakeResolver(PageBrainResolver):
    def __init__(self):
        super().__init__(browser=None)

    def find(self, target: dict):
        return [
            {"type": "css", "value": "#login", "visible": True, "enabled": True},
        ]


class OkHandler(IActionHandler):
    def execute(self, tool_call, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True)


def test_action_run_logged_with_pagebrain_and_healer(tmp_path: Path):
    logger = RunJsonlLogger(run_id="run-log", logs_dir=tmp_path)
    resolver = FakeResolver()
    handlers = {"click": OkHandler()}
    plan = [{"tool": "click", "args": {"target": {"text": "Login"}}}]
    ex = DeterministicPlanExecutor(log=logger, handlers=handlers, resolver=resolver, settings=None)
    res = ex.execute(plan, ctx=ExecCtx(run_id="run-log"))
    assert res and res[0].ok

    log_path = tmp_path / "run-run-log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    # find action.run event
    action_events = [json.loads(l) for l in lines if '"action.run"' in l]
    assert action_events, "action.run not logged"
    ev = action_events[0]
    assert ev["run_id"] == "run-log"
    assert ev["tool"] == "click"
    assert ev["executor"]["status"] == "passed"
    assert ev["executor"]["selector"]["value"] == "#login"

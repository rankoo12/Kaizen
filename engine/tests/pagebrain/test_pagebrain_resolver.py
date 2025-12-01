from __future__ import annotations

from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.commands.action_handler import IActionHandler, StepResult, ExecCtx
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor


class EvalBrowser:
    """Minimal browser stub exposing run_coro + evaluate for resolver.find()."""

    def run_coro(self, value):
        # resolver calls runner(eval_fn(script)); our eval_fn returns plain value
        return value

    async def open(self, url: str):
        pass

    def evaluate(self, script: str):
        s = str(script).lower()
        # Pretend only selectors that include input[value*="small" i] exist
        return ("input[value*" in s) and ("small" in s)


class OkHandler(IActionHandler):
    def execute(self, tool_call, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True)


def test_pagebrain_resolver_stores_metadata():
    r = PageBrainResolver(browser=EvalBrowser())
    out = r.find({"text": "small size"})
    assert isinstance(out, list) and len(out) >= 1
    sel = out[0]
    assert isinstance(sel, dict) and sel.get("type") == "css"
    meta = r.get_last_pagebrain()
    assert meta.get("candidate_count", 0) >= 1
    assert "chosen" in meta
    assert meta["chosen"]["selector"]["type"] == "css"


def test_pagebrain_metadata_flows_into_executor_meta():
    resolver = PageBrainResolver(browser=EvalBrowser())
    handlers = {"click": OkHandler()}
    plan = [{"tool": "click", "args": {"target": {"text": "small size"}}}]
    ex = DeterministicPlanExecutor(handlers=handlers, resolver=resolver, settings=None)
    res = ex.execute(plan, ctx=ExecCtx(run_id="run-1"))
    assert res and res[0].ok
    meta = plan[0].get("meta") or {}
    pb = meta.get("pagebrain") or {}
    assert pb.get("candidate_count", 0) >= 1
    assert "chosen" in pb

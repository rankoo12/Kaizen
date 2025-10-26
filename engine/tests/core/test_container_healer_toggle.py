from engine.core.config.container import Container
from engine.core.commands.action_handler import IActionHandler, ExecCtx, StepResult
from pathlib import Path


class OkClick(IActionHandler):
    def execute(self, tool_call: dict, ctx: ExecCtx) -> StepResult:
        return StepResult(ok=True, reason=None)


class ResolverZero:
    def find(self, target: dict):
        return []


def _make_plan():
    return [{"tool": "click", "args": {"target": {"text": "Login"}}}]


def test_container_healer_toggle_off_keeps_failure():
    c = Container()
    # Toggle off
    class _S:
        HEALER_ENABLED = False
        LOGS_DIR = Path("logs")
        SNAPSHOTS_DIR = Path("snapshots")

    c.settings.override(_S())
    # Provide simple handlers and resolver
    c.action_handlers.override({"click": OkClick()})
    c.element_resolver.override(ResolverZero())

    ex = c.plan_executor()
    res = ex.execute(_make_plan(), ctx=ExecCtx(run_id="r"))
    assert res[0].ok is False


def test_container_healer_toggle_on_heals():
    c = Container()
    # Toggle on
    class _S:
        HEALER_ENABLED = True
        LOGS_DIR = Path("logs")
        SNAPSHOTS_DIR = Path("snapshots")

    c.settings.override(_S())
    c.action_handlers.override({"click": OkClick()})
    c.element_resolver.override(ResolverZero())

    ex = c.plan_executor()
    res = ex.execute(_make_plan(), ctx=ExecCtx(run_id="r"))
    assert res[0].ok is True

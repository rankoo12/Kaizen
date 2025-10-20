from engine.core.config.container import Container


class FakeSettings:
    EXECUTION_PATH = "orchestrator"
    # satisfy other attributes if accessed by DI
    LOGS_DIR = None
    SNAPSHOTS_DIR = None


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
        return []


def test_live_runner_uses_orchestrator_when_toggled(monkeypatch):
    c = Container()

    # Override settings to enable orchestrator path
    c.settings.override(FakeSettings())

    # Inject fake executor to capture calls
    fake_exec = FakeExecutor()
    from dependency_injector import providers

    c.plan_executor.override(providers.Object(fake_exec))

    runner = c.live_runner()

    class Spec:
        id = "it-1"
        steps = []

    run_id = runner.run_sync(Spec())

    assert run_id == "run-it-1"
    assert len(fake_exec.calls) == 1
    plan, ctx = fake_exec.calls[0]
    assert isinstance(plan, list) and plan[0]["tool"] == "open"
    assert plan[0]["args"]["url"] == "about:blank"

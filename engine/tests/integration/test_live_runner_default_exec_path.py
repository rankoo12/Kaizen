from engine.core.config.container import Container


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, ctx):
        self.calls.append((plan, ctx))
        return []


def test_live_runner_defaults_to_orchestrator(monkeypatch):
    c = Container()

    # With default settings, EXECUTION_PATH should be 'orchestrator'
    # Override the plan executor to avoid real browser and capture calls
    from dependency_injector import providers

    fake_exec = FakeExecutor()
    c.plan_executor.override(providers.Object(fake_exec))

    runner = c.live_runner()

    class Spec:
        id = "d1"
        steps = []

    run_id = runner.run_sync(Spec())
    assert isinstance(run_id, str) and run_id.startswith("run-")
    assert len(fake_exec.calls) == 1
    plan, ctx = fake_exec.calls[0]
    assert plan[0]["tool"] == "open"
    assert plan[0]["args"]["url"] == "about:blank"

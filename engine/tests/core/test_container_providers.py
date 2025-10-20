from engine.core.config.container import Container


def test_resolve_snapshot_provider_is_callable():
    c = Container()
    fn = c.resolve_snapshot()
    assert callable(fn)

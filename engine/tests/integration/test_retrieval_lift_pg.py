import os
import pytest


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_retrieval_pg_lift_against_distractor(monkeypatch):
    psycopg = pytest.importorskip("psycopg")  # noqa: F841
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)

    from engine.core.storage.postgres import PostgresStorage
    from engine.core.healing.selector_healer import DeterministicHealer

    store = PostgresStorage(dsn)

    domain = "example.lift"
    tool = "click"

    # Seed two embedding selectors for the same domain/tool so retrieval must rank them
    good_sig = {"text": "Sign In"}
    good_sel = {"type": "css", "value": "#signin"}
    distractor_sig = {"text": "Checkout"}
    distractor_sel = {"type": "css", "value": "#checkout"}

    store.save_embedding_selector(
        domain=domain,
        tool=tool,
        target_signature=good_sig,
        selector=good_sel,
        tenant_id=None,
    )
    store.save_embedding_selector(
        domain=domain,
        tool=tool,
        target_signature=distractor_sig,
        selector=distractor_sel,
        tenant_id=None,
    )

    healer = DeterministicHealer(storage=store)

    # Query with slightly different case to exercise embedder similarity,
    # and ensure retrieval picks the intended selector over the distractor.
    failure = {"target": {"text": "sign in"}}
    ctx = {"tool": tool, "domain": domain, "tenant_id": None}

    res = healer.heal(failure, ctx)
    assert res is not None
    primary = res.get("primary") or {}
    assert primary.get("value") == "#signin"

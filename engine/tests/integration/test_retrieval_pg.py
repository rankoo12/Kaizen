import os
import pytest


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_retrieval_selector_resolves_from_embeddings(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)

    from engine.core.storage.postgres import PostgresStorage
    from engine.core.healing.selector_healer import DeterministicHealer

    st = PostgresStorage(dsn)
    # Seed an embedding mapping for domain/tool signature
    domain = "example.test"
    tool = "click"
    signature = {"text": "Sign In"}
    selector = {"type": "css", "value": "#signin"}
    st.save_embedding_selector(domain=domain, tool=tool, target_signature=signature, selector=selector, tenant_id=None)

    healer = DeterministicHealer(storage=st)
    # Query with a slightly different case to verify robust retrieval
    failure = {"target": {"text": "sign in"}}
    ctx = {"tool": tool, "domain": domain}
    res = healer.heal(failure, ctx)
    assert res is not None and res.get("primary", {}).get("value") == "#signin"

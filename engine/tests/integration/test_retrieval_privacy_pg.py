import os
import pytest


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_retrieval_respects_tenant_and_global_opt_in(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)

    from engine.core.storage.postgres import PostgresStorage
    from engine.core.healing.selector_healer import DeterministicHealer
    from engine.core.config.settings import settings

    st = PostgresStorage(dsn)
    healer = DeterministicHealer(storage=st)

    domain = "example.test"
    tool = "click"
    signature = {"text": "Join"}
    selector = {"type": "css", "value": "#join"}

    # Seed under tenant t1
    st.save_embedding_selector(domain=domain, tool=tool, target_signature=signature, selector=selector, tenant_id="t1")

    # Enforced multitenancy (no cross-tenant retrieval)
    monkeypatch.setenv("KAIZEN_MULTITENANT_ENFORCED", "true")
    # t2 requester -> None
    res = healer.heal({"target": {"text": "join"}}, {"tool": tool, "domain": domain, "tenant_id": "t2"})
    assert res is None
    # t1 requester -> hit
    res = healer.heal({"target": {"text": "join"}}, {"tool": tool, "domain": domain, "tenant_id": "t1"})
    assert res is not None and res.get("primary", {}).get("value") == "#join"

    # Not enforced, but no global opt-in -> still filter by tenant when provided; None when tenant differs
    monkeypatch.setenv("KAIZEN_MULTITENANT_ENFORCED", "false")
    res = healer.heal({"target": {"text": "join"}}, {"tool": tool, "domain": domain, "tenant_id": "t2"})
    assert (res is None) or (res.get("primary", {}).get("value") != "#join")

    # Enable global opt-in, allow cross-tenant when tenant_id None
    monkeypatch.setenv("KAIZEN_RETRIEVAL_GLOBAL_OPT_IN", "true")
    res = healer.heal({"target": {"text": "join"}}, {"tool": tool, "domain": domain, "tenant_id": None})
    assert res is not None and res.get("primary", {}).get("value") == "#join"

import os
import pytest


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_postgres_storage_basic_roundtrip():
    psycopg = pytest.importorskip("psycopg")
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping Postgres integration test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    from engine.core.storage.postgres import PostgresStorage

    store = PostgresStorage(dsn)

    run_id = store.start_run("pytest-sample", website="example.test")
    assert isinstance(run_id, str) and run_id
    store.finish_run(run_id, {"total": 1, "passed": 1, "failed": 0})
    doc = store.get_run(run_id)
    assert doc is not None and doc.get("status") == "finished"

    store.save_suite("suite-pg", {"id": "suite-pg", "steps": []})
    s = store.get_suite("suite-pg")
    assert s is not None and (s.get("spec") or {}).get("id") == "suite-pg"

    job_id = store.enqueue({"spec": {"id": "q1"}})
    job = store.next_job()
    assert job is not None and job.get("job_id") == job_id
    store.mark_running(job_id, run_id=run_id)
    store.complete(job_id, run_id=run_id)
    st = store.state()
    assert isinstance(st.get("queued"), list) and isinstance(st.get("running"), list)

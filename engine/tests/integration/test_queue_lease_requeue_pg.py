import os
import pytest


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v if v else None


@pytest.mark.integration
def test_queue_lease_requeues_stale_running_pg(monkeypatch):
    psycopg = pytest.importorskip("psycopg")  # noqa: F841
    if not _env("KAIZEN_PG_TEST", None):
        pytest.skip("KAIZEN_PG_TEST not set; skipping PG lease test")

    dsn = _env("KAIZEN_PG_DSN", "postgresql://kaizen:kaizen@localhost:5432/kaizen")
    monkeypatch.setenv("KAIZEN_PG_DSN", dsn)
    # Use a short lease so stale jobs are considered for requeue quickly
    monkeypatch.setenv("KAIZEN_QUEUE_LEASE_SEC", "1")

    import psycopg as _pg

    # Prepare queue with a single stale running job
    with _pg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM queue")
            job_id = "job-stale-lease"
            cur.execute(
                """
                INSERT INTO queue(job_id, payload, status, run_id, created_at, updated_at)
                VALUES (%s, %s::jsonb, 'running', NULL, NOW() - interval '3600 seconds', NOW() - interval '3600 seconds')
                """,
                (job_id, "{}"),
            )

    from engine.core.storage.postgres import PostgresStorage

    store = PostgresStorage(dsn)
    # next_job should requeue the stale running job and return it as queued
    job = store.next_job()
    assert job is not None
    assert job.get("job_id") == "job-stale-lease"

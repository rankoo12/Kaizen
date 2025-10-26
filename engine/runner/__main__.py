from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

import httpx

from engine.core.config.container import Container
from engine.core.reporting.reporter import IReporter, StepRun


class StatsCaptureReporter(IReporter):
    def __init__(self) -> None:
        self._last = None
        self._started: Dict[str, float] = {}
        self._on_start: Optional[callable] = None

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        self._started[str(run_id)] = time.time()
        if self._on_start:
            try:
                self._on_start(str(run_id))
            except Exception:
                pass

    def on_step(self, step_run: StepRun) -> None:
        pass

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self._last = {"run_id": run_id, "stats": dict(stats or {})}

    def on_finish(self, run_id: str) -> None:
        pass

    def last(self):
        return self._last


async def _run_job(api_base: str, job: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # mark job picked up
        try:
            await client.post(f"{api_base}/queue/running", json={"job_id": job.get("job_id")})
        except Exception:
            pass

        # Build isolated container per job for safety
        container = Container()
        reporter = StatsCaptureReporter()

        # when on_run_start fires (live path), update running with run_id
        async def _on_start_async(run_id: str):
            try:
                await client.post(f"{api_base}/queue/running", json={"job_id": job.get("job_id"), "run_id": run_id})
            except Exception:
                pass

        # bridge sync reporter callback to async
        loop = asyncio.get_event_loop()

        def _on_start(run_id: str):
            loop.create_task(_on_start_async(run_id))

        reporter._on_start = _on_start
        orchestrator = container.orchestrator(reporter=reporter)

        spec = job.get("spec") or {}
        mode = str(job.get("mode") or "snapshot").lower()

        run_id = None
        try:
            if mode == "live":
                # run in thread to avoid blocking loop
                run_id = await asyncio.to_thread(orchestrator.run_live, spec, None, url=job.get("url"))
            else:
                run_id = await asyncio.to_thread(
                    orchestrator.run_snapshot,
                    spec,
                    None,
                    html_path=job.get("html_path"),
                    html=job.get("html"),
                    snapshot_path=job.get("snapshot") or job.get("snapshot_path"),
                )
            # Post final stats
            last = reporter.last() or {"run_id": run_id, "stats": {}}
            payload = {"stats": last.get("stats", {})}
            try:
                await client.post(f"{api_base}/runs/{run_id}/finish", json=payload)
            except Exception:
                pass
        except Exception:
            # Best-effort failure record
            try:
                if run_id is None:
                    run_id = f"job-{job.get('job_id')}-error"
                await client.post(
                    f"{api_base}/runs/{run_id}/finish",
                    json={"stats": {"total": 0, "passed": 0, "failed": 1, "reasons": {"runner_error": 1}}},
                )
            except Exception:
                pass
        finally:
            try:
                await client.post(f"{api_base}/queue/complete", json={"job_id": job.get("job_id"), "run_id": run_id})
            except Exception:
                pass


async def _poll_and_run(api_base: str, interval: float = 1.0) -> None:
    # Concurrency control via env
    try:
        max_conc = max(1, int(os.environ.get("RUNNER_CONCURRENCY", "1")))
    except Exception:
        max_conc = 1

    tasks: set[asyncio.Task] = set()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            # prune done tasks
            done = {t for t in tasks if t.done()}
            tasks -= done

            # fill available slots
            while len(tasks) < max_conc:
                try:
                    r = await client.get(f"{api_base}/queue/next")
                    r.raise_for_status()
                    job = r.json().get("job")
                except Exception:
                    job = None
                if not job:
                    break
                t = asyncio.create_task(_run_job(api_base, job))
                tasks.add(t)

            if len(tasks) >= max_conc:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(interval)


def main() -> None:
    api_base = os.environ.get("KAIZEN_API_BASE", "http://engine-api:8080/api")
    asyncio.run(_poll_and_run(api_base))


if __name__ == "__main__":
    main()

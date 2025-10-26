from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict

import httpx

from engine.core.config.container import Container
from engine.core.reporting.reporter import IReporter, StepRun


class StatsCaptureReporter(IReporter):
    def __init__(self) -> None:
        self._last = None
        self._started: Dict[str, float] = {}

    def on_run_start(self, run_id: str, mode: str, **fields) -> None:
        self._started[str(run_id)] = time.time()

    def on_step(self, step_run: StepRun) -> None:
        pass

    def on_run_finish(self, run_id: str, stats: dict) -> None:
        self._last = {"run_id": run_id, "stats": dict(stats or {})}

    def on_finish(self, run_id: str) -> None:
        pass

    def last(self):
        return self._last


async def _poll_and_run(api_base: str, interval: float = 2.0) -> None:
    container = Container()
    # Create orchestrator with local reporter to capture stats
    reporter = StatsCaptureReporter()
    orchestrator = container.orchestrator(reporter=reporter)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                r = await client.get(f"{api_base}/queue/next")
                r.raise_for_status()
                job = r.json().get("job")
            except Exception:
                job = None

            if not job:
                await asyncio.sleep(interval)
                continue

            spec = job.get("spec") or {}
            mode = str(job.get("mode") or "snapshot").lower()

            try:
                if mode == "live":
                    run_id = orchestrator.run_live(spec, url=job.get("url"))
                else:
                    run_id = orchestrator.run_snapshot(
                        spec,
                        html_path=job.get("html_path"),
                        html=job.get("html"),
                        snapshot_path=job.get("snapshot") or job.get("snapshot_path"),
                    )
                # Post back final stats to API
                last = reporter.last() or {"run_id": run_id, "stats": {}}
                payload = {"stats": last.get("stats", {})}
                try:
                    await client.post(f"{api_base}/runs/{run_id}/finish", json=payload)
                except Exception:
                    pass
            except Exception:
                # If orchestration failed, still try to post a failure record
                try:
                    await client.post(f"{api_base}/runs/{run_id}/finish", json={"stats": {"total": 0, "passed": 0, "failed": 1, "reasons": {"runner_error": 1}}})
                except Exception:
                    pass


def main() -> None:
    api_base = os.environ.get("KAIZEN_API_BASE", "http://engine-api:8080/api")
    asyncio.run(_poll_and_run(api_base))


if __name__ == "__main__":
    main()

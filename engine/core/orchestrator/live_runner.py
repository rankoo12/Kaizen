import asyncio
from urllib.parse import quote
from engine.core.browser.browser_port import IBrowser
from engine.core.orchestrator.types import IPlanner, StepPlan, IOrchestrator
from engine.core.logging.log import ILog
from engine.core.config.settings import Settings, settings as _settings

OFFLINE_HTML = """<!doctype html><html><body>
<button id="login">Login</button>
<input name="q" />
</body></html>"""


class LiveRunner:
    def __init__(
        self,
        planner: IPlanner,
        browser: IBrowser,
        storage,
        log: ILog,
        orchestrator: IOrchestrator | None = None,
        settings: Settings = _settings,
    ):
        self._planner = planner
        self._browser = browser
        self._storage = storage
        self._log = log
        self._orchestrator = orchestrator
        self._settings = settings

    async def run(self, spec, url: str | None = None) -> str:
        # Optional delegation behind a safe toggle
        if (
            getattr(self._settings, "EXECUTION_PATH", "legacy") == "orchestrator"
            and self._orchestrator is not None
        ):
            return self._orchestrator.run_live(spec, url=url)
        self._log.info("Starting live run", test_id=spec.id)
        run_id = self._storage.start_run(test_id=spec.id)

        # Offline-safe default page
        target_url = url or f"data:text/html,{quote(OFFLINE_HTML)}"
        await self._browser.open(target_url)

        for i, step in enumerate(spec.steps):
            plan: StepPlan = self._planner.plan(step.text)
            query = plan.target_query

            if "click" in step.text.lower():
                await self._browser.click(query.get("selector", "#login"))
                action = "click"
            elif "type" in step.text.lower():
                await self._browser.type(
                    query.get("selector", "input[name='q']"), "test input"
                )
                action = "type"
            else:
                action = "noop"

            self._storage.record_step(
                {
                    "run_id": run_id,
                    "index": i,
                    "action": action,
                    "query": query,
                }
            )
            self._log.info("Step done", index=i, action=action)

        await self._browser.screenshot(f"{spec.id}_final.png")
        await self._browser.close()
        self._storage.finish_run(run_id)
        self._log.info("Live run finished", run_id=run_id)
        return run_id

    def run_sync(self, spec, url: str | None = None) -> str:
        return asyncio.run(self.run(spec, url=url))

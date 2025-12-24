import asyncio
from engine.core.orchestrator.types import IOrchestrator
from engine.core.logging.log import ILog
from engine.core.config.settings import Settings, settings as _settings


class LiveRunner:
    def __init__(
        self,
        planner,
        browser,
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
        if self._orchestrator is None:
            raise RuntimeError("LiveRunner requires an orchestrator")
        # Run blocking orchestrator path in a worker thread to avoid
        # interacting with the current event loop.
        return await asyncio.to_thread(self._orchestrator.run_live, spec, url=url)

    def run_sync(self, spec, url: str | None = None) -> str:
        if self._orchestrator is None:
            raise RuntimeError("LiveRunner requires an orchestrator")
        return self._orchestrator.run_live(spec, url=url)

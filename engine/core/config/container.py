from dependency_injector import containers, providers
from engine.core.config.settings import Settings
from engine.core.resolving.element_resolver import ElementResolver
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.orchestrator.types import IPlanner, IResolveSnapshot
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.orchestrator.live_runner import LiveRunner
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.logging.log import JsonlLogger, ILog
from engine.core.reporting.reporter import IReporter, RUN_REPORTER, InMemoryRunReporter, JsonlTailReporter
from engine.core.commands import OpenHandler, ClickHandler, TypeHandler, PressHandler
from engine.core.config.settings import settings
from engine.core.healing.selector_healer import DeterministicHealer
from engine.core.llm.ollama_text import OllamaTextAdapter


# Temporary stub for planner until integrated with real parsing logic
class SimplePlanner(IPlanner):
    def plan(self, step_text: str):
        from engine.core.orchestrator.types import StepPlan

        return StepPlan(target_query={"text": step_text})


def build_container() -> "Container":
    return Container()


def _resolve_snapshot_stub(
    *, plan, html_path=None, tolerance: float, healer_depth: int
):
    # Type-correct no-op result; preserves runner behavior until real pipeline lands
    return {
        "candidates": [],
        "reason": f"stub(plan={getattr(plan, 'target_query', {})}, "
        f"html_path={html_path}, tol={tolerance}, depth={healer_depth})",
    }


class StdoutLogger:
    def info(self, msg: str, **kv):
        print(f"[INFO] {msg}", kv)

    def warn(self, msg: str, **kv):
        print(f"[WARN] {msg}", kv)

    def error(self, msg: str, **kv):
        print(f"[ERROR] {msg}", kv)


class InMemoryStorage:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        # profiles: list of dicts with keys: domain, tool, target_signature, selector, hits, last_seen
        self._profiles: list[dict] = []

    def start_run(self, test_id):
        rid = f"run-{test_id}"
        self._runs[rid] = {"test_id": test_id, "started": True}
        return rid

    def record_step(self, step):
        return None

    def finish_run(self, run_id):
        rec = self._runs.get(str(run_id))
        if rec is not None:
            rec["finished"] = True

    # ---- Minimal Locator Profiles (in-memory) ----
    def save_locator_profile(self, *, domain, tool: str, target_signature: dict, selector: dict) -> None:
        import time as _time

        # normalize selector dict to minimal form
        sel_type = selector.get("type") if isinstance(selector, dict) else None
        sel_value = selector.get("value") if isinstance(selector, dict) else None
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return
        norm_sel = {"type": sel_type, "value": sel_value}
        now = _time.time()
        # dedupe by domain+tool+selector
        for row in self._profiles:
            if row["tool"] == tool and row.get("domain") == domain and row["selector"] == norm_sel:
                row["hits"] = int(row.get("hits", 0)) + 1
                row["last_seen"] = now
                return
        self._profiles.append({
            "domain": domain,
            "tool": tool,
            "target_signature": dict(target_signature or {}),
            "selector": norm_sel,
            "hits": 1,
            "last_seen": now,
        })

    def _sig_contains(self, sup: dict, sub: dict) -> bool:
        try:
            for k, v in (sub or {}).items():
                if k not in sup:
                    return False
                if sup[k] != v:
                    return False
            return True
        except Exception:
            return False

    def find_locator_profile(self, *, domain, tool: str, target_signature: dict):
        # Prefer domain match then global; prefer sig containment match; order by specificity then hits then last_seen
        matches = []
        for row in self._profiles:
            if row["tool"] != tool:
                continue
            dom_score = 1 if (row.get("domain") and row.get("domain") == domain) else (0 if row.get("domain") is None else -1)
            sig = row.get("target_signature") or {}
            if target_signature and self._sig_contains(sig, target_signature):
                # Prefer more specific stored signatures (row with more fields)
                try:
                    spec = len(sig)
                except Exception:
                    spec = 0
                matches.append((2 + dom_score, spec, int(row.get("hits", 0)), float(row.get("last_seen", 0.0)), row))
            elif not target_signature:
                # allow best-by-tool fallback
                matches.append((dom_score, 0, int(row.get("hits", 0)), float(row.get("last_seen", 0.0)), row))
        if not matches:
            # try global if we didn't match a scoped domain
            for row in self._profiles:
                if row["tool"] != tool:
                    continue
                if target_signature and self._sig_contains(row.get("target_signature") or {}, target_signature):
                    matches.append((0, len(target_signature), int(row.get("hits", 0)), float(row.get("last_seen", 0.0)), row))
                elif not target_signature:
                    matches.append((0, 0, int(row.get("hits", 0)), float(row.get("last_seen", 0.0)), row))
        if not matches:
            return None
        matches.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
        row = matches[0][-1]
        return dict(row.get("selector") or {})


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["engine"])

    # Expose Pydantic Settings instance from module (env-overridable via KAIZEN_*)
    settings = providers.Object(settings)

    # Default logger: JSONL structured logs to logs/{run_id}.jsonl
    logger: providers.Provider[ILog] = providers.Factory(
        JsonlLogger,
        logs_dir=settings.provided.LOGS_DIR,
    )

    # Reporter (optional) – override in apps/tests when needed
    def _build_reporter(settings_obj):
        backend = getattr(settings_obj, "REPORTER_BACKEND", "in_memory")
        if backend == "jsonl_tail":
            try:
                return JsonlTailReporter(events_path=settings_obj.LOGS_DIR / "runs_events.jsonl", resync_on_start=bool(getattr(settings_obj, "REPORTER_RESYNC_ON_START", False)))
            except Exception:
                return InMemoryRunReporter()
        return InMemoryRunReporter()

    reporter: providers.Provider[IReporter | None] = providers.Callable(_build_reporter, settings)

    element_resolver = providers.Factory(ElementResolver)

    # TODO: replace with actual resolve_snapshot service

    # Provide the callable directly for clarity
    resolve_snapshot = providers.Object(_resolve_snapshot_stub)

    planner = providers.Singleton(SimplePlanner)

    # Storage selection: Postgres when configured; fallback to in-memory
    def _build_storage(settings_obj):
        backend = getattr(settings_obj, "STORAGE_BACKEND", "auto")
        dsn = getattr(settings_obj, "PG_DSN", None)
        use_pg = (backend == "postgres") or (backend == "auto" and dsn)
        if use_pg and dsn:
            try:
                from engine.core.storage.postgres import PostgresStorage  # lazy import

                print("[storage] initializing PostgresStorage")
                return PostgresStorage(dsn)
            except Exception as e:
                print(f"[storage] PostgresStorage init failed, falling back to memory: {e}")
                return InMemoryStorage()
        return InMemoryStorage()

    storage = providers.Singleton(_build_storage, settings)

    # Playwright browser adapter (for Live Mode)
    playwright_browser = providers.Singleton(PlaywrightBrowser)

    # Concrete action handlers using shared Playwright browser
    open_handler = providers.Factory(OpenHandler, browser=playwright_browser)
    click_handler = providers.Factory(ClickHandler, browser=playwright_browser)
    type_handler = providers.Factory(TypeHandler, browser=playwright_browser)
    press_handler = providers.Factory(PressHandler, browser=playwright_browser)

    action_handlers = providers.Dict(
        open=open_handler,
        click=click_handler,
        type=type_handler,
        press=press_handler,
    )

    snapshot_runner = providers.Factory(
        SnapshotRunner,
        planner=planner,
        resolve_snapshot=resolve_snapshot,
        storage=storage,
        log=logger,
    )

    # Deterministic plan executor (stub) and high-level orchestrator
    healer = providers.Callable(
        lambda s, st: DeterministicHealer(storage=st) if getattr(s, "HEALER_ENABLED", False) else None,
        settings,
        storage,
    )
    plan_executor = providers.Factory(
        DeterministicPlanExecutor,
        browser=playwright_browser,
        handlers=action_handlers,
        resolver=element_resolver,
        log=logger,
        reporter=reporter,
        settings=settings,
        healer=healer,
        storage=storage,
    )

    # Optional LLM adapter for planner preview and future planner path
    llm_text = providers.Callable(
        lambda s: OllamaTextAdapter(
            getattr(s, "OLLAMA_BASE_URL", "http://ollama:11434"),
            getattr(s, "OLLAMA_MODEL", "llama3.1"),
            timeout=float(getattr(s, "LLM_TIMEOUT_SECONDS", 10.0) or 10.0),
        )
        if bool(getattr(s, "LLM_ENABLED", False))
        else None,
        settings,
    )

    orchestrator = providers.Factory(
        EngineOrchestrator,
        planner=planner,
        plan_executor=plan_executor,
        snapshot_runner=snapshot_runner,
        storage=storage,
        log=logger,
        reporter=reporter,
        llm=llm_text,
    )

    live_runner = providers.Factory(
        LiveRunner,
        planner=planner,
        browser=playwright_browser,
        storage=storage,
        log=logger,
        orchestrator=orchestrator,
        settings=settings,
    )

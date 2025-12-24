from dependency_injector import containers, providers
from engine.core.config.settings import Settings
from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.pagebrain.model_store import PageBrainModelStore
from engine.core.pagebrain.finder import PageBrainFinder
from engine.core.pagebrain.llm_ranker import (
    ILlmPageBrainRanker,
    NoopLlmPageBrainRanker,
    QwenLlmPageBrainRanker,
    OpenAiLlmPageBrainRanker,
)
from engine.core.orchestrator.snapshot_runner import SnapshotRunner
from engine.core.orchestrator.types import IPlanner, IResolveSnapshot
from engine.core.browser.playwright_driver import PlaywrightBrowser
from engine.core.orchestrator.live_runner import LiveRunner
from engine.core.orchestrator.plan_executor import DeterministicPlanExecutor
from engine.core.orchestrator.orchestrator import EngineOrchestrator
from engine.core.logging.log import JsonlLogger, ILog
from engine.core.reporting.reporter import (
    IReporter,
    RUN_REPORTER,
    InMemoryRunReporter,
    JsonlTailReporter,
)
from engine.core.commands import (
    OpenHandler,
    ClickHandler,
    TypeHandler,
    PressHandler,
    WaitForHandler,
    AssertVisibleHandler,
    AssertTextHandler,
    AssertUrlHandler,
    CustomHandler,
    DoubleClickHandler,
    RightClickHandler,
    HoverHandler,
    FocusHandler,
    BlurHandler,
    ClearHandler,
    SelectHandler,
    UploadHandler,
    DragHandler,
    DragAndDropHandler,
    ScrollHandler,
    ReloadHandler,
    BackHandler,
    ForwardHandler,
    NewTabHandler,
    NewWindowHandler,
    SwitchTabHandler,
    SwitchWindowHandler,
    CloseTabHandler,
    CloseWindowHandler,
    DownloadHandler,
)
from engine.core.config.settings import settings
from engine.core.healing.selector_healer import DeterministicHealer
from engine.core.resolving.snapshot_resolver import (
    resolve_snapshot as _resolve_snapshot_impl,
)
from engine.core.llm.ollama_text import OllamaTextAdapter
from engine.core.perception import PerceptionLayer
from engine.core.storage.memory import InMemoryStorage


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
    # Delegate to real implementation (static HTML candidate catalog + semantic resolve)
    try:
        return _resolve_snapshot_impl(
            plan=plan,
            html_path=html_path,
            tolerance=tolerance,
            healer_depth=healer_depth,
        )
    except Exception:
        # Best-effort fallback to an empty result to avoid breaking snapshot runs
        return {
            "candidates": [],
            "reason": "snapshot_resolver_error",
        }


class StdoutLogger:
    def info(self, msg: str, **kv):
        print(f"[INFO] {msg}", kv)

    def warn(self, msg: str, **kv):
        print(f"[WARN] {msg}", kv)

    def error(self, msg: str, **kv):
        print(f"[ERROR] {msg}", kv)


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
                return JsonlTailReporter(
                    events_path=settings_obj.LOGS_DIR / "runs_events.jsonl",
                    resync_on_start=bool(
                        getattr(settings_obj, "REPORTER_RESYNC_ON_START", False)
                    ),
                )
            except Exception:
                return InMemoryRunReporter()
        return InMemoryRunReporter()

    reporter: providers.Provider[IReporter | None] = providers.Callable(
        _build_reporter, settings
    )

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
                print(
                    f"[storage] PostgresStorage init failed, falling back to memory: {e}"
                )
                return InMemoryStorage()
        return InMemoryStorage()

    storage = providers.Singleton(_build_storage, settings)

    # Playwright browser adapter (for Live Mode)
    playwright_browser = providers.Singleton(PlaywrightBrowser)

    # Element resolver with access to browser (for lightweight live checks)
    # PageBrain v1 (heuristic + retrieval stub) resolver, compatible with IElementResolver
    def _build_model_store(settings_obj):
        try:
            default_model_id = getattr(settings_obj, "PAGEBRAIN_DEFAULT_MODEL", None)
            models_cfg = getattr(settings_obj, "PAGEBRAIN_MODELS", None)
            tenant_map = getattr(settings_obj, "PAGEBRAIN_TENANT_MODELS", None)
        except Exception:
            default_model_id = None
            models_cfg = None
            tenant_map = None
        store = PageBrainModelStore(default_model_id=default_model_id)
        try:
            if isinstance(models_cfg, dict):
                for mid, meta in models_cfg.items():
                    store.register_model(mid, meta)
        except Exception:
            pass
        if default_model_id:
            store.register_model(
                default_model_id,
                (
                    (models_cfg or {}).get(default_model_id)
                    if isinstance(models_cfg, dict)
                    else None
                ),
            )
        try:
            if isinstance(tenant_map, dict):
                for tid, mid in tenant_map.items():
                    store.set_model(tid, mid)
        except Exception:
            pass
        return store

    model_store = providers.Factory(_build_model_store, settings)

    def _build_llm_ranker(settings_obj: Settings) -> ILlmPageBrainRanker:
        """Build the LLM ranker implementation for PageBrain Finder.

        - When PAGEBRAIN_RANKER_MODE != 'llm' we always return a noop ranker so
          that PageBrainFinder will rely solely on the GBM/tabular fallback.
        - When PAGEBRAIN_RANKER_MODE == 'llm' and a PAGEBRAIN_LLM_MODEL is
          configured, we construct an HTTP-backed ranker:
          - OpenAiLlmPageBrainRanker when PAGEBRAIN_LLM_BACKEND='openai'.
          - QwenLlmPageBrainRanker for local OpenAI-compatible endpoints.
        """
        mode = getattr(settings_obj, "PAGEBRAIN_RANKER_MODE", "fallback")
        if str(mode) != "llm":
            return NoopLlmPageBrainRanker()

        model_id = getattr(settings_obj, "PAGEBRAIN_LLM_MODEL", None)
        if not isinstance(model_id, str) or not model_id.strip():
            # Misconfiguration: LLM mode requested but no model id provided.
            # Fall back to noop so that the container still builds and the
            # finder will rely on the deterministic ranker.
            return NoopLlmPageBrainRanker()

        backend = getattr(settings_obj, "PAGEBRAIN_LLM_BACKEND", "local_http")
        timeout = getattr(settings_obj, "PAGEBRAIN_LLM_TIMEOUT_SECONDS", 30.0)
        try:
            timeout_val = float(timeout)
        except Exception:
            timeout_val = 30.0

        # OpenAI backend (e.g. gpt-5-mini via the public API)
        if str(backend) == "openai":
            api_key = getattr(settings_obj, "PAGEBRAIN_LLM_API_KEY", None)
            if not isinstance(api_key, str) or not api_key.strip():
                # No key available: fail closed to noop to avoid accidental
                # unauthenticated calls.
                return NoopLlmPageBrainRanker()
            base_url = getattr(
                settings_obj,
                "PAGEBRAIN_LLM_BASE_URL",
                "https://api.openai.com",
            )
            return OpenAiLlmPageBrainRanker(
                api_key=api_key.strip(),
                model=model_id.strip(),
                base_url=str(base_url),
                timeout_seconds=timeout_val,
            )

        # Default: self-hosted OpenAI-compatible HTTP endpoint (e.g. vLLM + Qwen)
        base_url = getattr(
            settings_obj,
            "PAGEBRAIN_LLM_BASE_URL",
            "http://pagebrain-llm:9000",
        )
        return QwenLlmPageBrainRanker(
            base_url=str(base_url),
            model=model_id.strip(),
            timeout_seconds=timeout_val,
        )

    llm_ranker = providers.Factory(_build_llm_ranker, settings)

    def _build_element_resolver(
        settings_obj: Settings,
        browser_obj,
        model_store_obj: PageBrainModelStore,
        storage_obj,
        llm_ranker_obj: ILlmPageBrainRanker,
    ):
        """Select the element resolver/finder implementation.

        - When PAGEBRAIN_FINDER_PATH == 'finder_v2', use PageBrainFinder, which
          owns candidate collection and exposes richer decision metadata.
        - Otherwise fall back to PageBrainResolver (v1 behavior).
        """
        path = getattr(settings_obj, "PAGEBRAIN_FINDER_PATH", "resolver")
        if str(path) == "finder_v2":
            return PageBrainFinder(
                browser=browser_obj,
                model_store=model_store_obj,
                storage=storage_obj,
                llm_ranker=llm_ranker_obj,
                ranker_mode=str(getattr(settings_obj, "PAGEBRAIN_RANKER_MODE", "fallback")),
            )
        return PageBrainResolver(browser=browser_obj, model_store=model_store_obj)

    element_resolver = providers.Factory(
        _build_element_resolver,
        settings,
        playwright_browser,
        model_store,
        storage,
        llm_ranker,
    )

    # Concrete action handlers using shared Playwright browser
    open_handler = providers.Factory(OpenHandler, browser=playwright_browser)
    click_handler = providers.Factory(ClickHandler, browser=playwright_browser)
    type_handler = providers.Factory(TypeHandler, browser=playwright_browser)
    press_handler = providers.Factory(PressHandler, browser=playwright_browser)
    wait_handler = providers.Factory(WaitForHandler, browser=playwright_browser)
    assert_visible_handler = providers.Factory(
        AssertVisibleHandler, browser=playwright_browser
    )
    assert_text_handler = providers.Factory(
        AssertTextHandler, browser=playwright_browser
    )
    assert_url_handler = providers.Factory(AssertUrlHandler, browser=playwright_browser)
    custom_handler = providers.Factory(CustomHandler, browser=playwright_browser)
    dblclick_handler = providers.Factory(DoubleClickHandler, browser=playwright_browser)
    rightclick_handler = providers.Factory(
        RightClickHandler, browser=playwright_browser
    )
    hover_handler = providers.Factory(HoverHandler, browser=playwright_browser)
    focus_handler = providers.Factory(FocusHandler, browser=playwright_browser)
    blur_handler = providers.Factory(BlurHandler, browser=playwright_browser)
    clear_handler = providers.Factory(ClearHandler, browser=playwright_browser)
    select_handler = providers.Factory(SelectHandler, browser=playwright_browser)
    upload_handler = providers.Factory(UploadHandler, browser=playwright_browser)
    drag_handler = providers.Factory(DragHandler, browser=playwright_browser)
    dnd_handler = providers.Factory(DragAndDropHandler, browser=playwright_browser)
    scroll_handler = providers.Factory(ScrollHandler, browser=playwright_browser)
    reload_handler = providers.Factory(ReloadHandler, browser=playwright_browser)
    back_handler = providers.Factory(BackHandler, browser=playwright_browser)
    forward_handler = providers.Factory(ForwardHandler, browser=playwright_browser)
    newtab_handler = providers.Factory(NewTabHandler, browser=playwright_browser)
    newwin_handler = providers.Factory(NewWindowHandler, browser=playwright_browser)
    switchtab_handler = providers.Factory(SwitchTabHandler, browser=playwright_browser)
    switchwin_handler = providers.Factory(
        SwitchWindowHandler, browser=playwright_browser
    )
    closetab_handler = providers.Factory(CloseTabHandler, browser=playwright_browser)
    closewin_handler = providers.Factory(CloseWindowHandler, browser=playwright_browser)
    download_handler = providers.Factory(DownloadHandler, browser=playwright_browser)

    action_handlers = providers.Dict(
        open=open_handler,
        click=click_handler,
        type=type_handler,
        press=press_handler,
        waitFor=wait_handler,
        assertVisible=assert_visible_handler,
        assertText=assert_text_handler,
        assertUrl=assert_url_handler,
        custom=custom_handler,
        doubleClick=dblclick_handler,
        rightClick=rightclick_handler,
        hover=hover_handler,
        focus=focus_handler,
        blur=blur_handler,
        clear=clear_handler,
        select=select_handler,
        upload=upload_handler,
        drag=drag_handler,
        dragAndDrop=dnd_handler,
        scroll=scroll_handler,
        reload=reload_handler,
        back=back_handler,
        forward=forward_handler,
        newTab=newtab_handler,
        newWindow=newwin_handler,
        switchTab=switchtab_handler,
        switchWindow=switchwin_handler,
        closeTab=closetab_handler,
        closeWindow=closewin_handler,
        download=download_handler,
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
        lambda s, st: (
            DeterministicHealer(storage=st)
            if getattr(s, "HEALER_ENABLED", False)
            else None
        ),
        settings,
        storage,
    )
    perception_layer = providers.Factory(PerceptionLayer)
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
        perception_layer=perception_layer,
    )

    # Optional LLM adapter for planner preview and future planner path
    llm_text = providers.Callable(
        lambda s: (
            OllamaTextAdapter(
                getattr(s, "OLLAMA_BASE_URL", "http://ollama:11434"),
                getattr(s, "OLLAMA_MODEL", "llama3.1"),
                timeout=float(getattr(s, "LLM_TIMEOUT_SECONDS", 10.0) or 10.0),
                max_tokens=int(getattr(s, "LLM_MAX_TOKENS", 256) or 256),
                temperature=float(getattr(s, "LLM_TEMPERATURE", 0.2) or 0.2),
            )
            if bool(getattr(s, "LLM_ENABLED", False))
            else None
        ),
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

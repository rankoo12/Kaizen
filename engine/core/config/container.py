from dependency_injector import containers, providers
from engine.core.config.settings import Settings
from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.pagebrain.model_store import PageBrainModelStore
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


class InMemoryStorage:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        # profiles: list of dicts with keys: domain, tool, target_signature, selector, hits, last_seen
        self._profiles: list[dict] = []
        # per-action annotations for runs (dev-only, in-memory)
        self._annotations: list[dict] = []

    def start_run(self, test_id):
        import time as _time

        # Use timestamp-based suffix to avoid reusing the same run_id
        # across multiple executions of the same test (e.g., contract tests).
        ts = int(_time.time())
        rid = f"run-{ts}-{test_id}"
        self._runs[rid] = {"test_id": test_id, "started": True, "started_at": ts}
        return rid

    def record_step(self, step):
        return None

    def finish_run(self, run_id, stats: dict | None = None):
        rec = self._runs.get(str(run_id))
        if rec is not None:
            rec["finished"] = True
            if stats is not None:
                try:
                    rec["stats"] = dict(stats)
                except Exception:
                    rec["stats"] = stats

    # ---- Per-action annotations (in-memory) ----
    def save_run_action_annotation(
        self,
        *,
        run_id: str,
        action_index: int,
        label: str,
        source: str,
        notes: str | None = None,
        user_id: str | None = None,
        selector: dict | None = None,
        domain: str | None = None,
        tool: str | None = None,
        target_signature: dict | None = None,
    ) -> dict:
        import time as _time

        rid = str(run_id)
        idx = int(action_index)
        src = str(source)
        row = None
        for ann in self._annotations:
            if (
                ann.get("run_id") == rid
                and ann.get("action_index") == idx
                and ann.get("source") == src
            ):
                row = ann
                break
        if row is None:
            row = {
                "run_id": rid,
                "action_index": idx,
                "test_id": None,
                "step_id": None,
                "label": str(label),
                "source": src,
                "notes": notes,
                "user_id": user_id,
                "created_at": _time.time(),
                "selector": selector,
                "domain": domain,
                "tool": tool,
                "target_signature": target_signature,
            }
            self._annotations.append(row)
        else:
            row["label"] = str(label)
            row["notes"] = notes
            row["user_id"] = user_id
            row["created_at"] = _time.time()
            row["selector"] = selector if selector is not None else row.get("selector")
            row["domain"] = domain if domain is not None else row.get("domain")
            row["tool"] = tool if tool is not None else row.get("tool")
            row["target_signature"] = (
                target_signature if target_signature is not None else row.get("target_signature")
            )
        return dict(row)

    def get_run_action_annotations(self, run_id: str) -> list[dict]:
        rid = str(run_id)
        anns = [a for a in self._annotations if a.get("run_id") == rid]
        anns.sort(
            key=lambda a: (
                int(a.get("action_index", 0) or 0),
                float(a.get("created_at", 0.0) or 0.0),
            )
        )
        return [dict(a) for a in anns]

    def get_selector_feedback_for_test(self, test_id: str) -> dict:
        """In-memory stub: aggregate annotations by selector for a pseudo test_id.

        Since InMemoryStorage does not persist runs/tests, this groups on annotations
        whose test_id matches. Used only in dev/test environments.
        """
        fb: dict[str, dict[str, int]] = {}
        tid = str(test_id)
        for row in self._annotations:
            if str(row.get("test_id") or "") != tid:
                continue
            sel = row.get("selector") or {}
            if not isinstance(sel, dict):
                continue
            sel_type = sel.get("type")
            sel_value = sel.get("value")
            if not isinstance(sel_type, str) or not isinstance(sel_value, str):
                continue
            key = f"{sel_type}|{sel_value}"
            entry = fb.setdefault(key, {"passed": 0, "failed": 0, "total": 0})
            entry["total"] += 1
            lab = str(row.get("label") or "").lower()
            if lab == "passed":
                entry["passed"] += 1
            elif lab == "failed":
                entry["failed"] += 1
        return fb

    # ---- Minimal Locator Profiles (in-memory) ----
    def save_locator_profile(
        self, *, domain, tool: str, target_signature: dict, selector: dict
    ) -> None:
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
            if (
                row["tool"] == tool
                and row.get("domain") == domain
                and row["selector"] == norm_sel
            ):
                row["hits"] = int(row.get("hits", 0)) + 1
                row["last_seen"] = now
                return
        self._profiles.append(
            {
                "domain": domain,
                "tool": tool,
                "target_signature": dict(target_signature or {}),
                "selector": norm_sel,
                "hits": 1,
                "last_seen": now,
            }
        )

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
            dom_score = (
                1
                if (row.get("domain") and row.get("domain") == domain)
                else (0 if row.get("domain") is None else -1)
            )
            sig = row.get("target_signature") or {}
            if target_signature and self._sig_contains(sig, target_signature):
                # Prefer more specific stored signatures (row with more fields)
                try:
                    spec = len(sig)
                except Exception:
                    spec = 0
                matches.append(
                    (
                        2 + dom_score,
                        spec,
                        int(row.get("hits", 0)),
                        float(row.get("last_seen", 0.0)),
                        row,
                    )
                )
            elif not target_signature:
                # allow best-by-tool fallback
                matches.append(
                    (
                        dom_score,
                        0,
                        int(row.get("hits", 0)),
                        float(row.get("last_seen", 0.0)),
                        row,
                    )
                )
        if not matches:
            # try global if we didn't match a scoped domain
            for row in self._profiles:
                if row["tool"] != tool:
                    continue
                if target_signature and self._sig_contains(
                    row.get("target_signature") or {}, target_signature
                ):
                    matches.append(
                        (
                            0,
                            len(target_signature),
                            int(row.get("hits", 0)),
                            float(row.get("last_seen", 0.0)),
                            row,
                        )
                    )
                elif not target_signature:
                    matches.append(
                        (
                            0,
                            0,
                            int(row.get("hits", 0)),
                            float(row.get("last_seen", 0.0)),
                            row,
                        )
                    )
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
    element_resolver = providers.Factory(
        PageBrainResolver, browser=playwright_browser, model_store=model_store
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

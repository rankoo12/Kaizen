from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from engine.core.resolving.element_resolver import ElementResolver
from engine.core.pagebrain.model_store import PageBrainModelStore
from engine.core.pagebrain.llm_ranker import ILlmPageBrainRanker, LlmRankerResult, NoopLlmPageBrainRanker
from engine.eval.pagebrain_ranker import FEATURE_KEYS


class PageBrainFinder(ElementResolver):
    """PageBrain Finder v2 – primary candidate engine for live runs.

    Responsibilities:
    - Generate selector candidates from the live DOM.
    - Blend in direct hints from the target (css/id/testid).
    - Optionally add storage-backed candidates (profiles, retrieval).
    - Apply human feedback (Passed/Failed) as a filter.
    - Optionally re-rank candidates with a trained ML model.
    """

    def __init__(
        self,
        *,
        browser: Any | None = None,
        model_store: PageBrainModelStore | None = None,
        storage: Any | None = None,
        llm_ranker: ILlmPageBrainRanker | None = None,
        ranker_mode: str = "fallback",
    ) -> None:
        super().__init__(browser=browser)
        self._model_store = model_store
        self._storage = storage
        self._tenant_id: str | None = None
        self._last_decision: Dict[str, Any] = {}
        self._selector_feedback: Dict[str, Dict[str, Any]] = {}
        self._llm_ranker: ILlmPageBrainRanker = llm_ranker or NoopLlmPageBrainRanker()
        self._ranker_mode: str = ranker_mode

    # ---- hooks from orchestrator -------------------------------------------------

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id

    def set_selector_feedback(self, feedback: Dict[str, Any] | None) -> None:
        if isinstance(feedback, dict):
            self._selector_feedback = dict(feedback)
        else:
            self._selector_feedback = {}

    def get_last_pagebrain(self) -> Dict[str, Any]:
        return dict(self._last_decision or {})

    # ---- internal helpers --------------------------------------------------------

    def _selector_key(self, cand: dict) -> str | None:
        if not isinstance(cand, dict):
            return None
        sel_type = cand.get("type")
        sel_value = cand.get("value")
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return None
        return f"{sel_type}|{sel_value}"

    def _apply_feedback_penalty(self, candidates: List[Any]) -> List[Any]:
        fb = self._selector_feedback or {}
        if not fb or not candidates:
            return candidates
        kept: list[Any] = []
        for cand in candidates:
            key = self._selector_key(cand) or ""
            stats = fb.get(key) or {}
            try:
                failed = int(stats.get("failed", 0) or 0)
                passed = int(stats.get("passed", 0) or 0)
            except Exception:
                failed = 0
                passed = 0
            if failed > passed and (failed + passed) > 0:
                continue
            kept.append(cand)
        return kept or candidates

    def _sort_candidates_by_feedback(self, candidates: List[dict]) -> List[dict]:
        """Reorder candidates so that selectors with strong positive human
        feedback appear first.

        This is used when we intentionally skip the LLM because we already
        know (from prior runs) that certain selectors are good. In that
        case we want the deterministic path to pick those selectors
        consistently without invoking the GBM/tabular model.
        """
        fb = self._selector_feedback or {}
        if not isinstance(fb, dict) or not candidates:
            return candidates

        scored: list[tuple[tuple[int, int, int], int, dict]] = []
        untouched: list[tuple[int, dict]] = []
        for idx, cand in enumerate(candidates):
            key = self._selector_key(cand) or ""
            stats = fb.get(key) or {}
            try:
                passed = int(stats.get("passed", 0) or 0)
                failed = int(stats.get("failed", 0) or 0)
            except Exception:
                passed = 0
                failed = 0
            if passed <= 0 and failed <= 0:
                untouched.append((idx, cand))
                continue
            # Higher (passed - failed) first, then more passes, then fewer fails.
            score = (passed - failed, passed, -failed)
            scored.append((score, idx, cand))

        if not scored:
            return candidates

        # Sort by score only, relying on Python's stable sort to preserve
        # the original candidate order for ties. This avoids situations
        # where equally-rated selectors (e.g. multiple "passed" elements)
        # have their order arbitrarily flipped.
        scored.sort(key=lambda t: t[0], reverse=True)
        ordered: list[dict] = [c for _score, _idx, c in scored]
        # Preserve original order for candidates without stats.
        for _idx, cand in untouched:
            ordered.append(cand)
        return ordered

    def _has_strong_positive_feedback_for_candidates(self, candidates: List[dict]) -> bool:
        """Return True when any of the given candidates has clear human
        positive feedback (passed >= 1 and passed >= failed).

        Feedback is aggregated across runs per selector in
        `_selector_feedback`, which is populated from storage via
        DeterministicPlanExecutor.set_selector_feedback(). The intent is:

        - If a selector has already been confirmed by a human as "passed"
          for this test, we should trust the deterministic/fallback ranker
          and avoid spending tokens on the LLM for this step.
        """
        fb = self._selector_feedback or {}
        if not isinstance(fb, dict) or not candidates:
            return False
        for cand in candidates:
            key = self._selector_key(cand) or ""
            if not key or key not in fb:
                continue
            stats = fb.get(key) or {}
            try:
                passed = int(stats.get("passed", 0) or 0)
                failed = int(stats.get("failed", 0) or 0)
            except Exception:
                continue
            if passed >= 1 and passed >= failed:
                return True
        return False

    def _apply_tool_bias(self, candidates: List[dict], tool: str | None) -> List[dict]:
        """Light tool-aware filtering / reordering for better defaults.

        The goal is not to fully decide here, but to remove obviously
        incompatible candidates so that the LLM ranker works over a
        cleaner set.

        - For `type`, prefer text-entry controls (input/textarea) and
          deprioritize purely clickable widgets (anchors, icon buttons)
          when at least one text-entry element is present.
        """
        if not candidates:
            return candidates
        tname = (tool or "").strip().lower()
        if not tname:
            return candidates

        if tname == "type":
            text_like: List[dict] = []
            others: List[dict] = []
            for cand in candidates:
                if not isinstance(cand, dict):
                    others.append(cand)
                    continue
                tag = (cand.get("tag") or "").lower()
                # Common text-entry widgets; we may extend this list later.
                if tag in {"input", "textarea"}:
                    text_like.append(cand)
                else:
                    others.append(cand)
            # Only bias when we actually found text-entry options.
            if text_like:
                return text_like + others
        return candidates

    def _is_valid_css_selector(self, css: str) -> bool:
        """Return True when CSS parses in the current document (best-effort)."""
        if not isinstance(css, str) or not css.strip():
            return False
        if self._browser is None:
            return True
        try:
            runner = getattr(self._browser, "run_coro", None)
            eval_fn = getattr(self._browser, "evaluate", None)
            if not callable(runner) or not callable(eval_fn):
                return True
            import json as _json

            script = (
                "(function(){try{document.querySelector("
                + _json.dumps(css)
                + ");return true;}catch(e){return false;}})()"
            )
            return bool(runner(eval_fn(script)))
        except Exception:
            return True

    def _looks_like_plain_text_selector(self, value: str | None) -> bool:
        if not isinstance(value, str):
            return False
        v = value.strip()
        if not v:
            return False
        if any(ch in v for ch in "#.[>:=,"):
            return False
        if '"' in v or "'" in v:
            return True
        parts = [p for p in v.split() if p]
        return len(parts) >= 2

    def _is_page_ready_for_llm(self) -> bool:
        """Best-effort check that the live page is loaded before LLM calls."""
        if self._browser is None:
            return True
        try:
            runner = getattr(self._browser, "run_coro", None)
            eval_fn = getattr(self._browser, "evaluate", None)
            if not callable(runner) or not callable(eval_fn):
                return True
            probe = runner(
                eval_fn(
                    "(function(){const s=document.readyState||'';"
                    "const href=location.href||'';"
                    "const body=document.body||null;"
                    "const len=body && body.innerText ? body.innerText.trim().length : 0;"
                    "return {state:s, href:href, bodyLen:len};})();"
                )
            )
            if isinstance(probe, dict):
                state = str(probe.get("state") or "").lower()
                href = str(probe.get("href") or "").strip().lower()
                body_len = probe.get("bodyLen") or 0
                if href in {"about:blank", ""}:
                    return False
                if state not in {"interactive", "complete"}:
                    return False
                # Consider the page not ready when there's effectively no body content.
                if isinstance(body_len, (int, float)) and body_len <= 0:
                    return False
                return True
            if isinstance(probe, str):
                return probe.lower() in {"interactive", "complete"}
        except Exception:
            return True
        return False

    def _pick_by_ordinal_index(self, candidates: List[dict], intent: dict) -> int | None:
        """Return candidate index based on ordinal intent (1-based, or last)."""
        if not candidates or not isinstance(intent, dict):
            return None
        ordinal = intent.get("ordinal")
        position = str(intent.get("position") or "").strip().lower()
        try:
            if isinstance(ordinal, str) and ordinal.strip():
                ordinal = int(ordinal)
        except Exception:
            ordinal = None
        if position in {"last", "final"}:
            ordinal = -1
        if ordinal is None or int(ordinal) == 0:
            return None
        try:
            ordinal = int(ordinal)
        except Exception:
            return None

        ordered: list[tuple[int, int, float | None, float | None]] = []
        has_bbox = False
        for idx, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                continue
            if not bool(cand.get("visible", True)) or not bool(cand.get("enabled", True)):
                continue
            dom_index = cand.get("dom_index")
            try:
                order_index = int(dom_index) if dom_index is not None else idx
            except Exception:
                order_index = idx
            bbox = cand.get("bbox") or cand.get("rect")
            x = y = None
            if isinstance(bbox, dict):
                try:
                    x = float(bbox.get("x"))
                    y = float(bbox.get("y"))
                except Exception:
                    x = None
                    y = None
            if x is not None and y is not None:
                has_bbox = True
            ordered.append((order_index, idx, y, x))
        if not ordered:
            return None
        if has_bbox:
            inf = float("inf")
            ordered.sort(
                key=lambda t: (
                    t[2] if t[2] is not None else inf,
                    t[3] if t[3] is not None else inf,
                    t[0],
                    t[1],
                )
            )
        else:
            ordered.sort(key=lambda t: (t[0], t[1]))
        if ordinal < 0:
            return ordered[-1][1]
        pos = ordinal - 1
        if pos < 0 or pos >= len(ordered):
            return None
        return ordered[pos][1]

    def _is_clickable_candidate(self, cand: dict) -> bool:
        if not isinstance(cand, dict):
            return False
        tag = (cand.get("tag") or "").lower()
        role = (cand.get("role") or "").lower()
        input_type = (cand.get("input_type") or cand.get("type") or "").lower()
        if tag in {"button", "a"}:
            return True
        if role in {"button", "link", "menuitem", "tab"}:
            return True
        if tag == "input" and input_type in {"button", "submit", "image"}:
            return True
        return False

    def _find_clickable_in_row(self, candidates: List[dict], chosen_idx: int) -> int | None:
        if not candidates or chosen_idx < 0 or chosen_idx >= len(candidates):
            return None
        chosen = candidates[chosen_idx]
        if not isinstance(chosen, dict):
            return None
        bbox = chosen.get("bbox") or chosen.get("rect")
        if not isinstance(bbox, dict):
            return None
        try:
            y0 = float(bbox.get("y"))
            x0 = float(bbox.get("x"))
        except Exception:
            return None
        try:
            h0 = float(bbox.get("h")) if bbox.get("h") is not None else None
        except Exception:
            h0 = None
        tol = 8.0
        if h0 is not None and h0 > 0:
            tol = max(6.0, min(20.0, h0 * 0.4))
        best_idx = None
        best_dx = None
        for idx, cand in enumerate(candidates):
            if idx == chosen_idx or not isinstance(cand, dict):
                continue
            if not self._is_clickable_candidate(cand):
                continue
            cb = cand.get("bbox") or cand.get("rect")
            if not isinstance(cb, dict):
                continue
            try:
                y = float(cb.get("y"))
                x = float(cb.get("x"))
            except Exception:
                continue
            if abs(y - y0) > tol:
                continue
            dx = abs(x - x0)
            if best_dx is None or dx < best_dx:
                best_dx = dx
                best_idx = idx
        return best_idx

    def _extract_features(self, cand: dict) -> dict:
        val = cand.get("value") or cand.get("selector", {}).get("value")
        val_str = str(val or "")
        return {
            "rank": float(cand.get("rank", 0.0)),
            "selector_len": float(len(val_str)),
            "has_id": 1.0 if "#" in val_str else 0.0,
            "has_class": 1.0 if "." in val_str else 0.0,
            "has_attr": 1.0 if "[" in val_str else 0.0,
            "num_desc": float(val_str.count(" ")),
            "visible": 1.0 if cand.get("visible", True) else 0.0,
            "enabled": 1.0 if cand.get("enabled", True) else 0.0,
            "type_is_css": 1.0 if cand.get("type") == "css" else 0.0,
            "type_is_xpath": 1.0
            if isinstance(cand.get("type"), str)
            and "xpath" in cand.get("type").lower()
            else 0.0,
        }

    def _load_model_weights(self, model_obj: Any) -> dict | None:
        if isinstance(model_obj, dict):
            return model_obj.get("weights") or model_obj
        if isinstance(model_obj, str):
            path = Path(model_obj)
            try:
                if path.exists():
                    import json

                    return json.loads(path.read_text())
                return json.loads(model_obj)
            except Exception:
                return None
        return None

    def _rank_with_model(self, candidates: list[Any], model_obj: Any) -> list[Any] | None:
        weights = self._load_model_weights(model_obj)
        if not isinstance(weights, dict):
            return None
        scored: list[tuple[dict, float]] = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            feats = self._extract_features(cand)
            score = 0.0
            for key in FEATURE_KEYS:
                try:
                    score += float(weights.get(key, 0.0)) * float(feats.get(key, 0.0))
                except Exception:
                    continue
            scored.append((cand, score))
        if not scored:
            return None
        scored.sort(key=lambda t: t[1], reverse=True)
        ranked: list[dict] = []
        for rank, (cand, score) in enumerate(scored):
            c = dict(cand)
            c["rank"] = rank
            c["score"] = score
            ranked.append(c)
        return ranked

    def _augment_with_storage_candidates(
        self, candidates: List[dict], tool: str | None, domain: str | None
    ) -> List[dict]:
        """Best-effort enrichment with profile/retrieval-based selectors."""

        if not getattr(self, "_storage", None):
            return candidates
        tool_name = (tool or "").strip()
        if not tool_name:
            return candidates
        storage = self._storage
        seen_keys = {self._selector_key(c) for c in candidates if isinstance(c, dict)}

        # Locator profile candidate (per-domain/tool)
        try:
            prof_fn = getattr(storage, "find_locator_profile", None)
            if callable(prof_fn):
                prof = prof_fn(domain=domain, tool=tool_name, target_signature={})
                if isinstance(prof, dict):
                    if (
                        isinstance(prof.get("type"), str)
                        and prof.get("type") == "css"
                        and isinstance(prof.get("value"), str)
                        and (
                            self._looks_like_plain_text_selector(prof.get("value"))
                            or not self._is_valid_css_selector(prof.get("value"))
                        )
                    ):
                        prof = None
                key = self._selector_key(prof)
                if key and key not in seen_keys:
                    candidates.append(
                        {
                            "type": prof.get("type"),
                            "value": prof.get("value"),
                            "visible": prof.get("visible", True),
                            "enabled": prof.get("enabled", True),
                            "source": "profile",
                        }
                    )
                    seen_keys.add(key)
        except Exception:
            pass

        # Retrieval embedding candidate (cross-run similarity)
        try:
            retrieve_fn = getattr(storage, "retrieve_embedding_selector", None)
            if callable(retrieve_fn):
                sel = retrieve_fn(
                    domain=domain,
                    tool=tool_name,
                    target_signature={},
                    tenant_id=self._tenant_id,
                    top_k=1,
                )
                if isinstance(sel, dict):
                    if (
                        isinstance(sel.get("type"), str)
                        and sel.get("type") == "css"
                        and isinstance(sel.get("value"), str)
                        and (
                            self._looks_like_plain_text_selector(sel.get("value"))
                            or not self._is_valid_css_selector(sel.get("value"))
                        )
                    ):
                        sel = None
                    key = self._selector_key(sel)
                    if key and key not in seen_keys:
                        candidates.append(
                            {
                                "type": sel.get("type"),
                                "value": sel.get("value"),
                                "visible": sel.get("visible", True),
                                "enabled": sel.get("enabled", True),
                                "source": "retrieval",
                            }
                        )
                        seen_keys.add(key)
        except Exception:
            pass
        return candidates

    # ---- candidate generation ----------------------------------------------------

    def _build_direct_candidates(self, target: dict) -> List[dict]:
        """High-priority candidates derived directly from the target."""

        t = target or {}
        candidates: List[dict] = []

        # Explicit CSS – treat as a strong hint but still allow fallbacks.
        css = t.get("css") if isinstance(t.get("css"), str) else None
        if css and not self._looks_like_plain_text_selector(css):
            exists = True
            try:
                if self._browser is not None:
                    runner = getattr(self._browser, "run_coro", None)
                    eval_fn = getattr(self._browser, "evaluate", None)
                    if callable(runner) and callable(eval_fn):
                        import json as _json

                        # Validate selector syntax; return false on invalid CSS
                        script = (
                            "(function(){try{return Boolean(document.querySelector("
                            + _json.dumps(css)
                            + "));}catch(e){return false;}})()"
                        )
                        exists = bool(runner(eval_fn(script)))
            except Exception:
                exists = True
            if exists:
                candidates.append(
                    {
                        "type": "css",
                        "value": css,
                        "visible": True,
                        "enabled": True,
                        "tag": "*",
                        "classes": [],
                    }
                )

        attrs = t if isinstance(t, dict) else {}
        if attrs.get("id"):
            candidates.append(
                {
                    "type": "id",
                    "value": attrs.get("id"),
                    "visible": True,
                    "enabled": True,
                }
            )
        if attrs.get("testid"):
            candidates.append(
                {
                    "type": "testid",
                    "value": attrs.get("testid"),
                    "visible": True,
                    "enabled": True,
                }
            )
        return candidates

    def _scan_dom_candidates(self, target: dict) -> List[dict]:
        """Inspect the live DOM and synthesize CSS candidates."""

        attrs = target if isinstance(target, dict) else {}

        # DOM-backed candidate scan when browser is available
        try:
            if self._browser is not None:
                runner = getattr(self._browser, "run_coro", None)
                eval_fn = getattr(self._browser, "evaluate", None)
                if callable(runner) and callable(eval_fn):
                    import json as _json
                    import re as _re

                    ordinal_present = False
                    try:
                        intent = attrs.get("__intent") if isinstance(attrs, dict) else None
                        if isinstance(intent, dict):
                            position = str(intent.get("position") or "").strip().lower()
                            if position in {"last", "final"}:
                                ordinal_present = True
                            else:
                                raw_ord = intent.get("ordinal")
                                if isinstance(raw_ord, str):
                                    raw_ord = raw_ord.strip()
                                    if raw_ord:
                                        try:
                                            raw_ord = int(raw_ord)
                                        except Exception:
                                            raw_ord = None
                                if isinstance(raw_ord, int) and raw_ord != 0:
                                    ordinal_present = True
                    except Exception:
                        ordinal_present = False

                    selector = (
                        "input, select, textarea, button, a, [role=\"button\"]"
                        if not ordinal_present
                        else (
                            "input, select, textarea, button, a, video, li, article, section, div, span, "
                            "h1, h2, h3, h4, h5, h6, [role=\"button\"], [role=\"link\"], "
                            "[role=\"listitem\"], [role=\"option\"], [role=\"row\"], [role=\"gridcell\"], "
                            "[role=\"menuitem\"], [role=\"tab\"], [role=\"treeitem\"]"
                        )
                    )

                    catalog_script = (
                        "(function(){\n"
                        "  function vis(el){const cs=el.ownerDocument.defaultView.getComputedStyle(el);"
                        "if(cs.display==='none'||cs.visibility==='hidden')return false;"
                        "const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}\n"
                        "  function rect(el){try{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};}catch(e){return null}}\n"
                        "  function attrsMap(el){try{const out={};const attrs=el.attributes||[];"
                        "for(let i=0;i<attrs.length;i++){const a=attrs[i];if(!a)continue;"
                        "const n=(a.name||'');const v=(a.value||'');if(!n||!v)continue;"
                        "if(n.startsWith('data-')||n.startsWith('aria-')||n==='placeholder'||n==='autocomplete'||n==='name'||n==='role'||n==='type'){out[n]=v;}}"
                        "return out;}catch(e){return {}}}\n"
                        "  function labelsText(el){try{if(el.labels){return Array.from(el.labels)"
                        ".map(l=>(l.innerText||'').trim()).filter(Boolean);}const id=el.getAttribute('id');"
                        "if(id){return Array.from(document.querySelectorAll('label[for=\"'+id+'\"]'))"
                        ".map(l=>(l.innerText||'').trim()).filter(Boolean);}return []}catch(e){return []}}\n"
                        "  const nodes = Array.from(document.querySelectorAll("
                        f"{_json.dumps(selector)}));\n"
                        "  return nodes.map((el, i)=>({\n"
                        "    domIndex: i,\n"
                        "    rect: rect(el),\n"
                        "    attrs: attrsMap(el),\n"
                        "    tag: (el.tagName||'').toLowerCase(),\n"
                        "    id: el.id||'',\n"
                        "    classes: Array.from(el.classList||[]),\n"
                        "    role: (el.getAttribute('role')||'').toLowerCase(),\n"
                        "    type: (el.getAttribute('type')||'').toLowerCase(),\n"
                        "    name: el.getAttribute('name')||'',\n"
                        "    testid: el.getAttribute('data-testid')||el.getAttribute('testid')||'',\n"
                        "    ariaLabel: el.getAttribute('aria-label')||'',\n"
                        "    placeholder: el.getAttribute('placeholder')||'',\n"
                        "    valueAttr: el.getAttribute('value')||'',\n"
                        "    text: ((el.innerText||el.textContent)||'').trim(),\n"
                        "    labels: labelsText(el),\n"
                        "    svgClasses: (function(){try{return Array.from(el.querySelectorAll('svg'))"
                        ".map(s=>s.getAttribute('class')||'').join(' ')}catch(e){return ''}})(),\n"
                        "    visible: vis(el),\n"
                        "    enabled: !(el.disabled)\n"
                        "  }));\n"
                        "})()"
                    )
                    catalog = runner(eval_fn(catalog_script)) or []

                    # Prepare keywords from text
                    txt = attrs.get("text") if isinstance(attrs.get("text"), str) else None
                    if not txt:
                        step_text = attrs.get("__step_text")
                        if isinstance(step_text, str) and step_text.strip():
                            txt = step_text
                    norm = txt.strip() if isinstance(txt, str) else None
                    try:
                        tokens = _re.findall(r"[A-Za-z0-9]+", norm) if norm else []
                    except Exception:
                        tokens = []
                    kws = [k.lower() for k in tokens] if tokens else (
                        [] if not norm else [norm.lower()]
                    )

                    tool_name = ""
                    try:
                        raw_tool = attrs.get("__tool")
                        if isinstance(raw_tool, str):
                            tool_name = raw_tool.strip().lower()
                    except Exception:
                        tool_name = ""

                    list_roles = {
                        "listitem",
                        "option",
                        "row",
                        "gridcell",
                        "menuitem",
                        "tab",
                        "treeitem",
                        "link",
                        "button",
                    }
                    list_tags = {
                        "li",
                        "article",
                        "section",
                        "div",
                        "span",
                        "video",
                        "a",
                        "button",
                    }

                    def _contains_any(val: str) -> bool:
                        if not kws:
                            return False
                        try:
                            return any(k in (val or "").lower() for k in kws)
                        except Exception:
                            return False

                    def _score(c: dict) -> float:
                        # Invisible/disabled are not eligible
                        if not bool(c.get("visible", False)) or not bool(c.get("enabled", False)):
                            return -1.0
                        s = 0.0
                        if ordinal_present:
                            tag = (c.get("tag") or "").lower()
                            role = (c.get("role") or "").lower()
                            if tag in list_tags or role in list_roles:
                                s += 2.5
                        # Hard matches
                        if isinstance(attrs.get("testid"), str) and c.get("testid") == attrs.get("testid"):
                            s += 10
                        if isinstance(attrs.get("id"), str) and c.get("id") == attrs.get("id"):
                            s += 9
                        if isinstance(attrs.get("name"), str) and c.get("name") == attrs.get("name"):
                            s += 7
                        # Soft contains
                        if _contains_any(c.get("name", "")):
                            s += 5
                        if _contains_any(c.get("ariaLabel", "")):
                            s += 5
                        if _contains_any(c.get("placeholder", "")):
                            s += 4
                        # Descendant SVG classes (e.g., icon-search)
                        if _contains_any(c.get("svgClasses", "")):
                            s += 6
                        # Label/text
                        try:
                            labels = [str(x).lower() for x in (c.get("labels") or [])]
                        except Exception:
                            labels = []
                        if any(any(k in lab for k in kws) for lab in labels):
                            s += 6
                        if c.get("tag") in ("button", "a") and _contains_any(c.get("text", "")):
                            s += 6
                        elif _contains_any(c.get("text", "")):
                            s += 2
                        if c.get("role") == "button" and kws:
                            s += 2
                        # Radio/checkbox boosts
                        if c.get("tag") == "input" and c.get("type") in ("radio", "checkbox"):
                            if _contains_any(c.get("valueAttr", "")):
                                s += 6
                            if labels:
                                s += 1
                        # Type hints from text
                        if isinstance(norm, str) and norm:
                            ln = norm.lower()
                            if any(w in ln for w in ("email", "e-mail")) and c.get("type") == "email":
                                s += 2
                            if any(w in ln for w in ("phone", "tel", "mobile")) and c.get("type") == "tel":
                                s += 2
                            # Generic "search" queries: use tool-aware bias.
                            if "search" in ln:
                                tag = (c.get("tag") or "").lower()
                                role = (c.get("role") or "").lower()
                                if tool_name == "type":
                                    # For typing, strongly prefer text-entry fields.
                                    if tag in ("input", "textarea") or role in ("combobox", "searchbox"):
                                        s += 8
                                elif tool_name == "click":
                                    # For clicks, prefer clickable search controls over plain inputs.
                                    if tag in ("button", "a") or role in ("button", "link", "menuitem", "tab"):
                                        s += 8
                        return s

                    scored: list[tuple[dict, float]] = []
                    for c in catalog:
                        try:
                            sc = _score(c)
                        except Exception:
                            continue
                        if sc < 0.0:
                            continue
                        scored.append((c, sc))
                    if scored:
                        scored.sort(key=lambda t: t[1], reverse=True)
                        max_k = 50 if ordinal_present else 5
                        top = scored[: max(1, min(len(scored), max_k))]
                        dom_candidates: list[dict] = []
                        seen_selectors: set[str] = set()
                        for cand, _ in top:
                            tag = (cand.get("tag") or "*").lower()
                            if isinstance(cand.get("testid"), str) and cand.get("testid"):
                                sel = f'[data-testid="{cand.get("testid")}"]'
                            elif isinstance(cand.get("id"), str) and cand.get("id"):
                                sel = f'#{cand.get("id")}'
                            elif (
                                cand.get("labels")
                                and tag in ("input", "select", "textarea")
                                and isinstance(norm, str)
                                and norm
                            ):
                                try:
                                    lab = str((cand.get("labels") or [""])[0]).strip()
                                except Exception:
                                    lab = norm
                                sel = f'label:has-text("{lab}") {tag}'
                            elif isinstance(cand.get("name"), str) and cand.get("name"):
                                sel = f'{tag}[name="{cand.get("name")}"]'
                            elif isinstance(cand.get("ariaLabel"), str) and cand.get("ariaLabel"):
                                sel = f'{tag}[aria-label="{cand.get("ariaLabel")}"]'
                            elif isinstance(cand.get("placeholder"), str) and cand.get("placeholder"):
                                sel = f'{tag}[placeholder="{cand.get("placeholder")}"]'
                            elif (
                                tag == "input"
                                and cand.get("type") in ("radio", "checkbox")
                                and isinstance(norm, str)
                                and norm
                            ):
                                sel = f'input[type="{cand.get("type")}"][value*={_json.dumps(norm)} i]'
                            elif tag in ("button", "a") and isinstance(norm, str) and norm:
                                sel = f'{tag}:has-text("{norm}")'
                            else:
                                sel = tag or "*"
                            if not isinstance(sel, str) or not sel:
                                continue
                            if sel in seen_selectors:
                                continue
                            seen_selectors.add(sel)
                            rect = cand.get("rect") if isinstance(cand, dict) else None
                            bbox = rect if isinstance(rect, dict) else None
                            dom_candidates.append(
                                {
                                    "type": "css",
                                    "value": sel,
                                    "visible": bool(cand.get("visible", True)),
                                    "enabled": bool(cand.get("enabled", True)),
                                    "tag": cand.get("tag") or "*",
                                    "role": cand.get("role") or "",
                                    "input_type": cand.get("type") or "",
                                    "classes": cand.get("classes") or [],
                                    "dom_index": cand.get("domIndex"),
                                    "bbox": bbox,
                                    "attrs": cand.get("attrs") or {},
                                }
                            )
                        if dom_candidates:
                            return dom_candidates
        except Exception:
            pass

        # Fallback heuristics when DOM scan fails but we have target text.
        text = attrs.get("text")
        if isinstance(text, str) and text:
            norm = text.strip()
            lower = norm.lower()
            if lower == "input":
                return [
                    {
                        "type": "css",
                        "value": "input",
                        "visible": True,
                        "enabled": True,
                        "tag": "input",
                        "classes": [],
                    }
                ]
            try:
                import re as _re

                tokens = _re.findall(r"[A-Za-z]+", norm)
                kw = max(tokens, key=len) if tokens else norm
            except Exception:
                kw = norm

            try:
                runner = getattr(self._browser, "run_coro", None) if self._browser else None
                eval_fn = getattr(self._browser, "evaluate", None) if self._browser else None
                btn_css = f'button:has-text("{norm}")'
                a_css = f'a:has-text("{norm}")'
                if callable(runner) and callable(eval_fn):
                    import json as _json

                    for cand_css in (btn_css, a_css):
                        script = f"Boolean(document.querySelector({_json.dumps(cand_css)}))"
                        if bool(runner(eval_fn(script))):
                            return [
                                {
                                    "type": "css",
                                    "value": cand_css,
                                    "visible": True,
                                    "enabled": True,
                                    "tag": "button" if cand_css.startswith("button") else "a",
                                    "classes": [],
                                }
                            ]
            except Exception:
                pass

            label_css = f'label:has-text("{norm}") input'
            attr_css = (
                f'input[name*="{kw}" i], '
                f'input[aria-label*="{kw}" i], '
                f'input[placeholder*="{kw}" i], '
                f'input[value*="{kw}" i]'
            )
            try:
                runner = getattr(self._browser, "run_coro", None) if self._browser else None
                eval_fn = getattr(self._browser, "evaluate", None) if self._browser else None
                if callable(runner) and callable(eval_fn):
                    import json as _json

                    for cand_css in (label_css, attr_css):
                        script = f"Boolean(document.querySelector({_json.dumps(cand_css)}))"
                        if bool(runner(eval_fn(script))):
                            return [
                                {
                                    "type": "css",
                                    "value": cand_css,
                                    "visible": True,
                                    "enabled": True,
                                    "tag": "input",
                                    "classes": [],
                                }
                            ]
            except Exception:
                pass
            return [
                {
                    "type": "css",
                    "value": label_css,
                    "visible": True,
                    "enabled": True,
                    "tag": "input",
                    "classes": [],
                }
            ]
        return []

    # ---- core API ----------------------------------------------------------------

    def find(self, target: dict) -> List[Any]:
        """Return the chosen candidate as a single-element list."""

        t = target or {}

        # Debug markers used in healer tests – keep behaviour but let PageBrain
        # own the logging and choice.
        try:
            dbg_text = t.get("text") if isinstance(t.get("text"), str) else None
            dbg_css = t.get("css") if isinstance(t.get("css"), str) else None
            marker = dbg_text or dbg_css
        except Exception:
            marker = None

        if marker in {"[heal-zero]", "[heal:none]"}:
            debug_candidates: List[dict] = []
        elif marker in {"[heal-multi]", "[heal:multi]"}:
            debug_candidates = [
                {"type": "css", "value": "#a", "visible": True, "enabled": True},
                {"type": "css", "value": "#b", "visible": True, "enabled": True},
            ]
        elif marker in {"[heal-hidden]", "[heal:hidden]"}:
            debug_candidates = [
                {
                    "type": "css",
                    "value": "#hidden",
                    "visible": False,
                    "enabled": True,
                }
            ]
        else:
            debug_candidates = None

        if debug_candidates is not None:
            chosen = debug_candidates[0] if debug_candidates else None
            ranked_dbg: List[Dict[str, Any]] = []
            for rank, cand in enumerate(debug_candidates[:5]):
                if not isinstance(cand, dict):
                    continue
                ranked_dbg.append(
                    {
                        "rank": rank,
                        "selector": {
                            "type": cand.get("type"),
                            "value": cand.get("value"),
                        },
                        "visible": cand.get("visible"),
                        "enabled": cand.get("enabled"),
                        "source": cand.get("source"),
                    }
                )
            decision_dbg: Dict[str, Any] = {
                "path": "pagebrain_finder_v2",
                "reason": "finder_v2_debug_marker",
                "candidate_count": len(debug_candidates),
                "candidates": ranked_dbg,
                "model_id": None,
                "tenant_id": self._tenant_id,
                "engine": "debug_marker",
                "chosen_index": 0 if chosen is not None else None,
            }
            if chosen is not None and isinstance(chosen, dict):
                decision_dbg["chosen"] = {
                    "selector": {
                        "type": chosen.get("type"),
                        "value": chosen.get("value"),
                    },
                    "visible": chosen.get("visible"),
                    "enabled": chosen.get("enabled"),
                }
            self._last_decision = decision_dbg
            return [chosen] if chosen is not None else []

        # Base candidates from direct hints + live DOM scan
        direct_candidates = self._build_direct_candidates(t)
        dom_candidates = self._scan_dom_candidates(t)

        base_candidates: List[dict] = []
        seen_keys = set()
        for cand in direct_candidates + dom_candidates:
            if not isinstance(cand, dict):
                continue
            key = self._selector_key(cand)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            base_candidates.append(cand)

        # Tool/domain hints injected by the executor (when available)
        tool = None
        domain = None
        try:
            if isinstance(target, dict):
                tool = target.get("__tool")
                domain = target.get("__domain")
        except Exception:
            tool = None
            domain = None

        # Start from base candidates then optionally add storage-driven ones
        candidates_with_storage = self._augment_with_storage_candidates(
            list(base_candidates),
            tool=str(tool or ""),
            domain=domain if isinstance(domain, str) else None,
        )

        # Apply simple feedback-based filtering when available
        candidates = self._apply_feedback_penalty(candidates_with_storage)

        # Light tool-aware biasing so that the LLM ranker operates on a
        # cleaner set (e.g., prefer inputs for `type`).
        candidates = self._apply_tool_bias(candidates, tool if isinstance(tool, str) else None)

        # Optional LLM scoring when enabled; falls back to GBM/tabular on failure.
        model_id = None
        engine = "fallback_ranker"
        llm_usage: Dict[str, Any] | None = None
        llm_decision: str | None = None
        # LLM usage is decided per-step by the executor (via locked selectors);
        # do not skip LLM globally based on test-level feedback.
        if self._ranker_mode == "llm" and candidates:
            if not self._is_page_ready_for_llm():
                llm_decision = "skipped_page_not_ready"
            else:
                try:
                    llm_result: LlmRankerResult | None = self._llm_ranker.rank(
                        target=t,
                        candidates=candidates,
                        dom_context={"tool": tool, "domain": domain} if tool or domain else None,
                        perception=None,
                    )
                except Exception:
                    llm_result = None
                if llm_result and llm_result.ranking:
                    # Reorder candidates according to the LLM-provided ranking.
                    try:
                        raw_meta = llm_result.raw if isinstance(llm_result.raw, dict) else {}
                        decision_tag = str(raw_meta.get("llm_decision") or "used")
                        model_id = raw_meta.get("model_id")
                        usage = raw_meta.get("usage")
                        if isinstance(usage, dict):
                            llm_usage = usage

                        # When the LLM explicitly signals that it needs more data
                        # or that constraints were violated, we treat the ranking
                        # as diagnostic only and fall back to the GBM/tabular
                        # ranker for the actual choice.
                        if decision_tag.startswith("discarded_"):
                            engine = "fallback_ranker"
                            llm_decision = decision_tag
                        else:
                            ordered: List[dict] = []
                            for idx in llm_result.ranking:
                                if isinstance(idx, int) and 0 <= idx < len(candidates):
                                    ordered.append(candidates[idx])
                            # Keep any remaining candidates in original order.
                            if len(ordered) < len(candidates):
                                seen = {id(c) for c in ordered}
                                for cand in candidates:
                                    if id(cand) not in seen:
                                        ordered.append(cand)
                            candidates = ordered
                            engine = "llm_ranker"
                            llm_decision = decision_tag
                    except Exception:
                        # Fall through to GBM/tabular ranker
                        engine = "fallback_ranker"

        if engine != "llm_ranker":
            try:
                if self._model_store is not None and candidates:
                    model_id = self._model_store.get_model(self._tenant_id)
                    model_obj = self._model_store.get_model_obj(self._tenant_id)
                    if model_obj:
                        ranked = self._rank_with_model(candidates, model_obj)
                        if ranked:
                            candidates = ranked
                            engine = "fallback_ranker"
            except Exception:
                model_id = None

        # Choose candidate, optionally honoring ordinal intent.
        chosen_idx: int | None = None
        intent = None
        try:
            if isinstance(t, dict):
                intent = t.get("__intent")
        except Exception:
            intent = None
        if isinstance(intent, dict):
            chosen_idx = self._pick_by_ordinal_index(candidates, intent)
            # If ordinal intent is for a click, prefer a clickable element
            # within the same visual row (best-effort).
            if (
                chosen_idx is not None
                and isinstance(tool, str)
                and tool.strip().lower() == "click"
            ):
                cand = candidates[chosen_idx] if chosen_idx < len(candidates) else None
                if isinstance(cand, dict) and not self._is_clickable_candidate(cand):
                    alt = self._find_clickable_in_row(candidates, chosen_idx)
                    if alt is not None:
                        chosen_idx = alt

        # Fallback: pick the first visible+enabled candidate when possible.
        if chosen_idx is None:
            for idx, cand in enumerate(candidates):
                if not isinstance(cand, dict):
                    continue
                if bool(cand.get("visible", True)) and bool(cand.get("enabled", True)):
                    chosen_idx = idx
                    break
            if chosen_idx is None and candidates:
                chosen_idx = 0

        chosen = (
            candidates[chosen_idx]
            if chosen_idx is not None and 0 <= chosen_idx < len(candidates)
            else None
        )

        # Build a compact ranking view for logs (top N only to keep payloads small)
        ranked: List[Dict[str, Any]] = []
        for rank, cand in enumerate(candidates[:5]):
            if not isinstance(cand, dict):
                continue
            ranked.append(
                {
                    "rank": rank,
                    "selector": {
                        "type": cand.get("type"),
                        "value": cand.get("value"),
                    },
                    "visible": cand.get("visible"),
                    "enabled": cand.get("enabled"),
                    "source": cand.get("source"),
                }
            )

        decision: Dict[str, Any] = {
            "path": "pagebrain_finder_v2",
            "reason": "finder_v2_dom_storage_feedback_model",
            "candidate_count": len(candidates),
            "candidates": ranked,
            "model_id": model_id,
            "tenant_id": self._tenant_id,
            "engine": engine,
            "chosen_index": chosen_idx,
        }
        if llm_usage is not None:
            decision["llm_usage"] = llm_usage
        if llm_decision is not None:
            decision["llm_decision"] = llm_decision
        if isinstance(intent, dict) and intent:
            decision["intent"] = intent
        if chosen is not None and isinstance(chosen, dict):
            decision["chosen"] = {
                "selector": {
                    "type": chosen.get("type"),
                    "value": chosen.get("value"),
                },
                "visible": chosen.get("visible"),
                "enabled": chosen.get("enabled"),
            }
        self._last_decision = decision

        # Preserve executor contract: either [] or [single_candidate]
        return [chosen] if chosen is not None else []

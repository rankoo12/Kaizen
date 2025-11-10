from typing import Protocol, List, Any
from ..types.dtos import TargetQuery, LocatorCandidates, Locator
from engine.core.browser.browser_port import IBrowser
from .strategies.semantic import SemanticStrategy, IResolverStrategy
from .strategies.attributes import AttributeStrategy
from .strategies.label_text import LabelTextStrategy
from .strategies.structural import StructuralStrategy


class IElementResolver(Protocol):
    """Turn a TargetQuery into ranked LocatorCandidates using strategies."""

    def resolve(
        self, query: TargetQuery, snapshot: "PageSnapshot"
    ) -> LocatorCandidates: ...

    def find(self, target: dict) -> list[Any]: ...


class ElementResolver:
    """Combines strategies; returns primary + fallbacks with a reason and confidence."""

    def __init__(self, strategies: List[IResolverStrategy] | None = None, browser: IBrowser | None = None):
        self._strategies: List[IResolverStrategy] = strategies or [
            AttributeStrategy(),
            LabelTextStrategy(),
            StructuralStrategy(),
            SemanticStrategy(),
        ]
        self._browser: IBrowser | None = browser

    def resolve(
        self, query: TargetQuery, snapshot: "PageSnapshot"
    ) -> LocatorCandidates:
        catalog = snapshot.get("candidates", [])
        if not catalog:
            raise ValueError("Empty catalog in snapshot")

        # Combine multiple strategies with simple weights
        weights = {
            AttributeStrategy: 1.0,
            LabelTextStrategy: 0.9,
            StructuralStrategy: 0.7,
            SemanticStrategy: 0.5,
        }
        agg: dict[int, float] = {}
        ref: dict[int, dict] = {}
        for strat in self._strategies:
            try:
                s_list = strat.score(query, catalog)
            except Exception:
                s_list = []
            w = weights.get(type(strat), 0.5)
            for c, s in s_list:
                key = id(c)
                agg[key] = agg.get(key, 0.0) + (float(s) * w)
                ref[key] = c
        combined = sorted(((ref[k], v) for k, v in agg.items()), key=lambda t: t[1], reverse=True)
        best, best_score = combined[0]
        others = [c for c, _ in combined[1:5]]

        primary: Locator = self._to_locator(best)
        fallbacks: List[Locator] = [self._to_locator(c) for c in others]

        reason = f"LayeredStrategies score={best_score:.2f} for text='{query.get('text','')}'"
        confidence = float(max(best_score, 0.0)) / (abs(best_score) + 10.0)

        return {
            "primary": primary,
            "fallbacks": fallbacks,
            "confidence": min(confidence, 1.0),
            "reason": reason,
            "bbox": best.get("bbox"),
        }

    # Minimal live find() for interactive tools. This enhanced stub does not
    # query a DOM, but synthesizes more realistic selectors based on common form
    # patterns so that execution succeeds on typical pages (e.g., httpbin form).
    def find(self, target: dict) -> list[Any]:
        t = target or {}
        # Debug triggers to exercise healing paths in dev/testing
        try:
            dbg_text = t.get("text") if isinstance(t.get("text"), str) else None
            dbg_css = t.get("css") if isinstance(t.get("css"), str) else None
            marker = dbg_text or dbg_css
            if marker in {"[heal-zero]", "[heal:none]"}:
                return []
            if marker in {"[heal-multi]", "[heal:multi]"}:
                return [
                    {"type": "css", "value": "#a", "visible": True, "enabled": True},
                    {"type": "css", "value": "#b", "visible": True, "enabled": True},
                ]
            if marker in {"[heal-hidden]", "[heal:hidden]"}:
                return [
                    {"type": "css", "value": "#hidden", "visible": False, "enabled": True}
                ]
        except Exception:
            pass
        # Prefer explicit CSS if present
        css = t.get("css") if isinstance(t.get("css"), str) else None
        if css:
            # If we can check presence via browser, do it; otherwise return as-is
            exists = True
            try:
                if self._browser is not None:
                    runner = getattr(self._browser, "run_coro", None)
                    eval_fn = getattr(self._browser, "evaluate", None)
                    if callable(runner) and callable(eval_fn):
                        import json as _json

                        script = f"Boolean(document.querySelector({_json.dumps(css)}))"
                        exists = bool(runner(eval_fn(script)))
            except Exception:
                exists = True
            if exists:
                return [
                    {
                        "type": "css",
                        "value": css,
                        "visible": True,
                        "enabled": True,
                        "tag": "*",
                        "classes": [],
                    }
                ]
        # Fallback to id/testid/text heuristics to synthesize a selector
        attrs = t if isinstance(t, dict) else {}
        if attrs.get("id"):
            return [
                {
                    "type": "id",
                    "value": attrs.get("id"),
                    "visible": True,
                    "enabled": True,
                }
            ]
        if attrs.get("testid"):
            return [
                {
                    "type": "testid",
                    "value": attrs.get("testid"),
                    "visible": True,
                    "enabled": True,
                }
            ]
        # DOM-backed candidate scan when browser is available
        try:
            if self._browser is not None:
                runner = getattr(self._browser, "run_coro", None)
                eval_fn = getattr(self._browser, "evaluate", None)
                if callable(runner) and callable(eval_fn):
                    import json as _json
                    import re as _re

                    # Build a rich candidate catalog and score it in Python
                    catalog_script = (
                        "(function(){\n"
                        "  function vis(el){const cs=el.ownerDocument.defaultView.getComputedStyle(el);if(cs.display==='none'||cs.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}\n"
                        "  function labelsText(el){try{if(el.labels){return Array.from(el.labels).map(l=>(l.innerText||'').trim()).filter(Boolean);}const id=el.getAttribute('id');if(id){return Array.from(document.querySelectorAll('label[for=\"'+id+'\"]')).map(l=>(l.innerText||'').trim()).filter(Boolean);}return []}catch(e){return []}}\n"
                        "  const nodes = Array.from(document.querySelectorAll('input, select, textarea, button, a, [role=\"button\"]'));\n"
                        "  return nodes.map(el=>({\n"
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
                        "    svgClasses: (function(){try{return Array.from(el.querySelectorAll('svg')).map(s=>s.getAttribute('class')||'').join(' ')}catch(e){return ''}})(),\n"
                        "    visible: vis(el),\n"
                        "    enabled: !(el.disabled)\n"
                        "  }));\n"
                        "})()"
                    )
                    catalog = runner(eval_fn(catalog_script)) or []

                    # Prepare keywords from text
                    txt = t.get("text") if isinstance(t.get("text"), str) else None
                    norm = txt.strip() if isinstance(txt, str) else None
                    try:
                        tokens = _re.findall(r"[A-Za-z0-9]+", norm) if norm else []
                    except Exception:
                        tokens = []
                    kws = [k.lower() for k in tokens] if tokens else ([] if not norm else [norm.lower()])

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
                        # Hard matches
                        if isinstance(t.get("testid"), str) and c.get("testid") == t.get("testid"):
                            s += 10
                        if isinstance(t.get("id"), str) and c.get("id") == t.get("id"):
                            s += 9
                        if isinstance(t.get("name"), str) and c.get("name") == t.get("name"):
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
                        return s

                    best = None
                    best_s = -1.0
                    for c in catalog:
                        try:
                            sc = _score(c)
                            if sc > best_s:
                                best_s = sc
                                best = c
                        except Exception:
                            continue
                    if best and best_s >= 0:
                        # Build selector from best candidate
                        tag = (best.get("tag") or "*").lower()
                        sel = None
                        if isinstance(best.get("testid"), str) and best.get("testid"):
                            sel = f"[data-testid=\"{best.get('testid')}\"]"
                        elif isinstance(best.get("id"), str) and best.get("id"):
                            sel = f"#{best.get('id')}"
                        elif (best.get("labels") and tag in ("input", "select", "textarea") and isinstance(norm, str) and norm):
                            try:
                                lab = str((best.get("labels") or [""])[0]).strip()
                            except Exception:
                                lab = norm
                            sel = f'label:has-text("{lab}") {tag}'
                        elif isinstance(best.get("name"), str) and best.get("name"):
                            sel = f"{tag}[name=\"{best.get('name')}\"]"
                        elif isinstance(best.get("ariaLabel"), str) and best.get("ariaLabel"):
                            sel = f"{tag}[aria-label=\"{best.get('ariaLabel')}\"]"
                        elif isinstance(best.get("placeholder"), str) and best.get("placeholder"):
                            sel = f"{tag}[placeholder=\"{best.get('placeholder')}\"]"
                        elif tag == "input" and best.get("type") in ("radio", "checkbox") and isinstance(norm, str) and norm:
                            import json as _json
                            sel = f"input[type=\"{best.get('type')}\"][value*={_json.dumps(norm)} i]"
                        elif tag in ("button", "a") and isinstance(norm, str) and norm:
                            sel = f"{tag}:has-text(\"{norm}\")"
                        else:
                            sel = tag or "*"
                        return [
                            {
                                "type": "css",
                                "value": sel,
                                "visible": bool(best.get("visible", True)),
                                "enabled": bool(best.get("enabled", True)),
                                "tag": best.get("tag") or "*",
                                "classes": best.get("classes") or [],
                            }
                        ]
        except Exception:
            pass

        text = attrs.get("text")
        if isinstance(text, str) and text:
            norm = text.strip()
            lower = norm.lower()
            if lower == "input":
                # Generic input
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
            # Normalize phrases like "the Name field" -> "Name"
            try:
                import re as _re

                tokens = _re.findall(r"[A-Za-z]+", norm)
                kw = max(tokens, key=len) if tokens else norm
            except Exception:
                kw = norm
            # Attempt clickable matches first (buttons/links) using text, then fallback to inputs
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

            # Prefer label association first (robust)
            label_css = f'label:has-text("{norm}") input'
            attr_css = f'input[name*="{kw}" i], input[aria-label*="{kw}" i], input[placeholder*="{kw}" i], input[value*="{kw}" i]'
            # If possible, verify presence and pick first that exists
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
            # Fallback to label-based selector without verifying
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

    @staticmethod
    def _to_locator(candidate: dict) -> Locator:
        # Prefer testid, then id, then role+text fallback
        attrs = candidate.get("attrs") or {}
        if attrs.get("testid"):
            return {"type": "testid", "value": attrs["testid"]}
        if candidate.get("id"):
            return {"type": "id", "value": candidate["id"]}
        # Special handling for radios/checkboxes with value/name hints
        tag = candidate.get("tag") or "*"
        ctype = (candidate.get("type") or "").lower()
        if tag == "input" and ctype in ("radio", "checkbox"):
            try:
                import json as _json

                val = candidate.get("value") or (candidate.get("valueAttr") if isinstance(candidate.get("valueAttr"), str) else None)
                if isinstance(val, str) and val:
                    return {"type": "css", "value": f"input[type=\"{ctype}\"][value*={_json.dumps(val)} i]"}
            except Exception:
                pass
            if isinstance(candidate.get("name"), str) and candidate.get("name"):
                return {"type": "css", "value": f"input[type=\"{ctype}\"][name=\"{candidate.get('name')}\"]"}
        # fallback to a rough css by tag + class
        classes = candidate.get("classes") or []
        cls_sel = ".".join([c for c in classes if c])
        css = tag + (("." + cls_sel) if cls_sel else "")
        return {"type": "css", "value": css}

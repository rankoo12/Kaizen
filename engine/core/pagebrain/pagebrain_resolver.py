from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from engine.core.resolving.element_resolver import ElementResolver
from engine.core.pagebrain.model_store import PageBrainModelStore
from engine.eval.pagebrain_ranker import FEATURE_KEYS


class PageBrainResolver(ElementResolver):
    """PageBrain v1: heuristic + profiles + retrieval stub wrapping ElementResolver.

    Captures basic metadata about chosen selector/candidates and optionally
    records which PageBrain model was selected for the current tenant.
    """

    def __init__(
        self,
        *args,
        model_store: PageBrainModelStore | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._last_pagebrain: Dict[str, Any] = {}
        self._tenant_id: str | None = None
        self._model_store = model_store
        self._model_cache: Dict[str, Any] = {}
        # Aggregated selector feedback for this run/test, keyed by "type|value"
        self._selector_feedback: Dict[str, Dict[str, Any]] = {}

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id

    def set_selector_feedback(self, feedback: Dict[str, Any] | None) -> None:
        """Inject aggregated human feedback per selector for this run/test.

        Expected shape: { "type|value": {"passed": int, "failed": int, "total": int}, ... }.
        """
        if isinstance(feedback, dict):
            self._selector_feedback = dict(feedback)
        else:
            self._selector_feedback = {}

    def _resolve_candidates(self, target: dict) -> list[Any]:
        return super().find(target) or []

    def _selector_key(self, cand: dict) -> str | None:
        if not isinstance(cand, dict):
            return None
        sel_type = cand.get("type")
        sel_value = cand.get("value")
        if not isinstance(sel_type, str) or not isinstance(sel_value, str):
            return None
        return f"{sel_type}|{sel_value}"

    def _apply_feedback_penalty(self, candidates: list[Any]) -> list[Any]:
        """Filter or down-weight candidates based on human feedback.

        Simple rule: if a selector has more 'failed' than 'passed' votes for
        this test, drop it from the candidate list. If all candidates would be
        dropped, fall back to the original list.
        """
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
            # Drop selectors that have been marked failed more often than passed
            if failed > passed and (failed + passed) > 0:
                continue
            kept.append(cand)
        return kept or candidates

    def find(self, target: dict) -> list[Any]:
        # Base candidates from live resolver
        candidates = self._resolve_candidates(target)

        model_id = None
        model_meta: dict | None = None
        try:
            if self._model_store is not None:
                model_id = self._model_store.get_model(self._tenant_id)
                model_obj = self._model_store.get_model_obj(self._tenant_id)
                model_meta = {"id": model_id, "loaded": bool(model_obj)}
                if model_obj:
                    ranked_candidates = self._rank_with_model(candidates, model_obj)
                    if ranked_candidates:
                        candidates = ranked_candidates
        except Exception:
            model_id = None
            model_meta = None

        # Apply human feedback-based penalties (drop historically failed selectors)
        candidates = self._apply_feedback_penalty(candidates)
        chosen = candidates[0] if candidates else None

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
                }
            )

        self._last_pagebrain = {
            "path": "pagebrain_v1",
            "reason": "heuristics+profiles+retrieval_stub",
            "candidate_count": len(candidates),
            "candidates": ranked,
            "model_id": model_id,
            "model_info": model_meta,
        }
        if chosen and isinstance(chosen, dict):
            self._last_pagebrain["chosen"] = {
                "selector": {
                    "type": chosen.get("type"),
                    "value": chosen.get("value"),
                },
                "visible": chosen.get("visible"),
                "enabled": chosen.get("enabled"),
            }
        return [chosen] if chosen else []

    def get_last_pagebrain(self) -> Dict[str, Any]:
        return dict(self._last_pagebrain or {})

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
            "type_is_xpath": 1.0 if isinstance(cand.get("type"), str) and "xpath" in cand.get("type").lower() else 0.0,
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
        scored = []
        for cand in candidates:
            feats = self._extract_features(cand)
            score = 0.0
            for key in FEATURE_KEYS:
                try:
                    score += float(weights.get(key, 0.0)) * float(feats.get(key, 0.0))
                except Exception:
                    continue
            scored.append((cand, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        ranked = []
        for rank, (cand, score) in enumerate(scored):
            c = dict(cand)
            c["rank"] = rank
            c["score"] = score
            ranked.append(c)
        return ranked

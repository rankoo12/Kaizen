from __future__ import annotations

from typing import Any, Dict, List

from engine.core.resolving.element_resolver import ElementResolver
from engine.core.pagebrain.model_store import PageBrainModelStore


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

    def set_tenant(self, tenant_id: str | None) -> None:
        self._tenant_id = tenant_id

    def find(self, target: dict) -> list[Any]:
        candidates = super().find(target) or []
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

        model_id = None
        model_info = None
        try:
            if self._model_store is not None:
                model_id = self._model_store.get_model(self._tenant_id)
                model_info = self._model_store.get_model_obj(self._tenant_id)
        except Exception:
            model_id = None
            model_info = None

        self._last_pagebrain = {
            "path": "pagebrain_v1",
            "reason": "heuristics+profiles+retrieval_stub",
            "candidate_count": len(candidates),
            "candidates": ranked,
            "model_id": model_id,
            "model_info": model_info,
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

from __future__ import annotations

from typing import Any, Dict, List

from engine.core.resolving.element_resolver import ElementResolver


class PageBrainResolver(ElementResolver):
    """PageBrain v1: heuristic + profiles + retrieval stub wrapping ElementResolver.

    For now this wraps the existing ElementResolver and captures basic metadata
    about the chosen selector and the small candidate set so downstream logging
    (StepRun/ActionRun) can include a PageBrain block. Future iterations can
    enrich scoring with retrieval and ML.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_pagebrain: Dict[str, Any] = {}

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

        self._last_pagebrain = {
            "path": "pagebrain_v1",
            "reason": "heuristics+profiles+retrieval_stub",
            "candidate_count": len(candidates),
            "candidates": ranked,
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

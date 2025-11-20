from __future__ import annotations

from typing import Dict


class PageBrainModelStore:
    """Minimal in-memory model registry with per-tenant overrides."""

    def __init__(self, default_model_id=None) -> None:
        self._default = default_model_id
        self._tenant_models: Dict[str, str] = {}

    def set_model(self, tenant_id: str, model_id: str) -> None:
        if not tenant_id or not model_id:
            return
        self._tenant_models[str(tenant_id)] = str(model_id)

    def get_model(self, tenant_id: str | None) -> str | None:
        if tenant_id and str(tenant_id) in self._tenant_models:
            return self._tenant_models[str(tenant_id)]
        return self._default

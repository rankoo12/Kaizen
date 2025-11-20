from __future__ import annotations

from typing import Dict


class PageBrainModelStore:
    """Minimal in-memory model registry with per-tenant overrides."""

    def __init__(self, default_model_id=None) -> None:
        self._default = default_model_id
        self._tenant_models: Dict[str, str] = {}
        self._models: Dict[str, object] = {}

    def register_model(self, model_id: str, model_obj: object | None = None) -> None:
        """Register a model artifact by id (object may be a stub/path)."""
        if not model_id:
            return
        key = str(model_id)
        if model_obj is not None:
            self._models[key] = model_obj
        else:
            self._models.setdefault(key, True)

    def set_model(self, tenant_id: str, model_id: str) -> None:
        if not tenant_id or not model_id:
            return
        self.register_model(model_id)
        self._tenant_models[str(tenant_id)] = str(model_id)

    def get_model(self, tenant_id: str | None) -> str | None:
        if tenant_id and str(tenant_id) in self._tenant_models:
            return self._tenant_models[str(tenant_id)]
        return self._default

    def get_model_obj(self, tenant_id: str | None):
        model_id = self.get_model(tenant_id)
        if model_id is None:
            return None
        return self._models.get(model_id)

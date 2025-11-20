from engine.core.pagebrain.model_store import PageBrainModelStore


def test_model_store_returns_defaults_and_overrides():
    store = PageBrainModelStore(default_model_id="global-model")
    # register a real model object for default
    store.register_model("global-model", model_obj={"path": "global.pb"})
    assert store.get_model(None) == "global-model"
    assert store.get_model_obj(None) == {"path": "global.pb"}
    assert store.get_model("tenant-1") == "global-model"
    store.set_model("tenant-1", "tenant-model")
    store.register_model("tenant-model", model_obj={"path": "tenant.pb"})
    assert store.get_model("tenant-1") == "tenant-model"
    assert store.get_model_obj("tenant-1") == {"path": "tenant.pb"}
    # other tenant still sees default
    assert store.get_model("tenant-2") == "global-model"
    assert store.get_model_obj("tenant-2") == {"path": "global.pb"}

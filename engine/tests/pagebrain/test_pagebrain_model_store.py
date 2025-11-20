from engine.core.pagebrain.model_store import PageBrainModelStore


def test_model_store_returns_defaults_and_overrides():
    store = PageBrainModelStore(default_model_id="global-model")
    assert store.get_model(None) == "global-model"
    assert store.get_model("tenant-1") == "global-model"
    store.set_model("tenant-1", "tenant-model")
    assert store.get_model("tenant-1") == "tenant-model"
    # other tenant still sees default
    assert store.get_model("tenant-2") == "global-model"

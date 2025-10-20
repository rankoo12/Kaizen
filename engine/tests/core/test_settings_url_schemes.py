from engine.core.config.settings import Settings


def test_allowed_url_schemes_env_string_parsing():
    s = Settings(ALLOWED_URL_SCHEMES="data:, about:blank , file:")
    assert s.ALLOWED_URL_SCHEMES == ["data:", "about:blank", "file:"]


def test_allowed_url_schemes_list_kept_as_is():
    s = Settings(ALLOWED_URL_SCHEMES=["data:", "about:blank", "file:"])
    assert s.ALLOWED_URL_SCHEMES == ["data:", "about:blank", "file:"]


def test_allowed_url_schemes_ignores_empty_entries():
    s = Settings(ALLOWED_URL_SCHEMES="data:,, about:blank , ,")
    assert s.ALLOWED_URL_SCHEMES == ["data:", "about:blank"]

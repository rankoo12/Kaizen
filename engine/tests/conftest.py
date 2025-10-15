import pytest
from engine.core.config.container import build_container


@pytest.fixture(scope="session")
def container():
    return build_container()

from dependency_injector import containers, providers
from .settings import Settings
from engine.core.resolving.element_resolver import (
    ElementResolver,
)  # uses your existing file


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["engine"])
    settings = providers.Singleton(Settings)
    element_resolver = providers.Factory(ElementResolver)


def build_container() -> Container:
    return Container()

from dependency_injector import containers, providers
from .settings import Settings


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["engine"])
    settings = providers.Singleton(Settings)
    # providers for interfaces (bound later when implementations land)
    # e.g., text_llm = providers.Factory(OllamaTextLLM, host=settings().OLLAMA_HOST, model=settings().LLM_TEXT_MODEL)

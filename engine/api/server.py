from fastapi import FastAPI
from .routes.resolve import register_resolve_routes


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kaizen Engine",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        ax_request_size=5 * 1024 * 1024,
    )

    # DI: prefer container if available; fall back to direct import
    resolver = None
    try:
        from engine.core.config.container import (
            build_container,
        )  # existing module in your tree

        container = build_container()
        resolver = container.resolve(
            "element_resolver"
        )  # expect your container to expose this key
    except Exception:
        # Minimal fallback (not validated): try direct ctor
        from engine.core.resolving.element_resolver import ElementResolver

        resolver = (
            ElementResolver()
        )  # if your resolver needs deps, adjust container instead

    register_resolve_routes(app, resolver)
    return app


# local-only runner
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8080)

from fastapi import FastAPI
from engine.api.routes.resolve import register_resolve_routes
from engine.api.routes.system import router as system_router
from engine.api.routes.metrics import router as metrics_router
from engine.api.routes.metrics import router as metrics_router
from engine.core.config.container import Container


def create_app(resolver=None) -> FastAPI:
    app = FastAPI(
        title="Kaizen Engine API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        max_request_size=10 * 1024 * 1024,
    )

    if resolver is None:
        container = Container()
        resolver = container.element_resolver()

    # Register routes
    register_resolve_routes(app, resolver)
    app.include_router(system_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8080)

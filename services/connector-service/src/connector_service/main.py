"""connector-service FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared_config import ConnectorServiceSettings

from connector_service import routes
from connector_service.registry import ConnectorRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = ConnectorServiceSettings()
    registry = ConnectorRegistry(settings=settings)
    registry.build()

    # Backwards-compat: expose the primary M365-compatible connector on the
    # existing /connector/* routes. Named connectors available via registry.
    primary = registry.get_primary_m365()
    if primary is not None:
        routes.set_connector(primary)

    routes.set_registry(registry)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA Connector Service",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    return app


app = create_app()


def run() -> None:
    import uvicorn
    settings = ConnectorServiceSettings()
    uvicorn.run(
        "connector_service.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.reload,
    )


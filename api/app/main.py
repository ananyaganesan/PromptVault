"""PromptVault API application factory and entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.config import Settings, get_settings
from api.app.db.pool import PoolFactory, create_pool
from api.app.dependencies.request_context import RequestIdMiddleware
from api.app.errors import install_exception_handlers
from api.app.logging_config import RequestLoggingMiddleware, configure_logging
from api.app.routers.health import router as health_router


def create_app(
    settings: Settings | None = None,
    *,
    pool_factory: PoolFactory = create_pool,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    if resolved_settings.environment != "test":
        configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        pool = pool_factory(resolved_settings)
        await pool.open(wait=True)
        application.state.db_pool = pool
        try:
            yield
        finally:
            await pool.close()

    expose_docs = resolved_settings.environment != "production"
    application = FastAPI(
        title="PromptVault API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    application.state.settings = resolved_settings
    install_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(health_router)
    return application


app = create_app()

"""PromptVault API application factory and entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.auth_rate_limits import (
    AuthRateLimitMiddleware,
    RateLimitStore,
    create_rate_limit_store,
)
from api.app.config import Settings, get_settings
from api.app.db.pool import PoolFactory, create_pool
from api.app.dependencies.request_context import RequestIdMiddleware
from api.app.errors import error_responses, install_exception_handlers
from api.app.logging_config import RequestLoggingMiddleware, configure_logging
from api.app.metrics import ApplicationMetrics, RequestMetricsMiddleware
from api.app.request_limits import RequestBodyLimitMiddleware
from api.app.routers.admin import router as admin_router
from api.app.routers.auth import router as auth_router
from api.app.routers.dashboard import router as dashboard_router
from api.app.routers.deployments import router as deployments_router
from api.app.routers.health import router as health_router
from api.app.routers.metrics import router as metrics_router
from api.app.routers.projects import router as projects_router
from api.app.routers.prompts import router as prompts_router
from api.app.routers.runs import router as runs_router
from api.app.routers.serve import router as serve_router
from api.app.routers.tokens import router as tokens_router
from api.app.routers.versions import router as versions_router


def create_app(
    settings: Settings | None = None,
    *,
    pool_factory: PoolFactory = create_pool,
    rate_limit_store: RateLimitStore | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    if resolved_settings.environment != "test":
        configure_logging(resolved_settings.log_level)
    resolved_rate_limit_store = rate_limit_store or create_rate_limit_store(
        resolved_settings.rate_limit_redis_url.get_secret_value()
        if resolved_settings.rate_limit_redis_url
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        pool = pool_factory(resolved_settings)
        await pool.open(wait=True)
        application.state.db_pool = pool
        try:
            yield
        finally:
            await pool.close()
            await resolved_rate_limit_store.close()

    expose_docs = resolved_settings.environment != "production"
    application = FastAPI(
        title="PromptVault API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
        responses=error_responses(413),
    )
    application.state.settings = resolved_settings
    application_metrics = ApplicationMetrics()
    application.state.metrics = application_metrics
    install_exception_handlers(application)
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=resolved_settings.max_request_body_bytes,
    )
    application.add_middleware(
        AuthRateLimitMiddleware,
        auth_requests=resolved_settings.auth_rate_limit_requests,
        auth_window_seconds=resolved_settings.auth_rate_limit_window_seconds,
        reset_requests=resolved_settings.password_reset_rate_limit_requests,
        reset_window_seconds=resolved_settings.password_reset_rate_limit_window_seconds,
        store=resolved_rate_limit_store,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["ETag", "X-Request-ID"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestMetricsMiddleware, metrics=application_metrics)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(health_router)
    application.include_router(metrics_router)
    application.include_router(auth_router)
    application.include_router(projects_router)
    application.include_router(prompts_router)
    application.include_router(versions_router)
    application.include_router(runs_router)
    application.include_router(dashboard_router)
    application.include_router(deployments_router)
    application.include_router(admin_router)
    application.include_router(tokens_router)
    application.include_router(serve_router)
    return application


app = create_app()

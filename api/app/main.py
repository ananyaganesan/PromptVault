"""PromptVault API application factory and entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.app.config import Settings, get_settings
from api.app.db.pool import PoolFactory, create_pool


def create_app(
    settings: Settings | None = None,
    *,
    pool_factory: PoolFactory = create_pool,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        pool = pool_factory(resolved_settings)
        await pool.open(wait=True)
        application.state.db_pool = pool
        try:
            yield
        finally:
            await pool.close()

    application = FastAPI(title="PromptVault API", version="0.1.0", lifespan=lifespan)
    application.state.settings = resolved_settings
    return application


app = create_app()

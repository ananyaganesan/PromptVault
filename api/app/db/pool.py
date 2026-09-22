"""Database pool construction and FastAPI access."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, cast

from api.app.config import Settings
from fastapi import Request
from psycopg_pool import AsyncConnectionPool


class PoolProtocol(Protocol):
    async def open(self, *, wait: bool = True) -> None: ...

    async def close(self) -> None: ...

    def connection(self) -> AbstractAsyncContextManager[Any]: ...


PoolFactory = Callable[[Settings], PoolProtocol]


def create_pool(settings: Settings) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_pool_timeout_seconds,
        open=False,
        kwargs={"autocommit": False},
    )


def get_pool(request: Request) -> PoolProtocol:
    return cast(PoolProtocol, request.app.state.db_pool)

"""Database pool construction and FastAPI access."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol, cast

from api.app.config import Settings
from api.app.db.orm import ORMConnection
from fastapi import Request


class PoolProtocol(Protocol):
    async def open(self, *, wait: bool = True) -> None: ...

    async def close(self) -> None: ...

    def connection(self) -> AbstractAsyncContextManager[Any]: ...


PoolFactory = Callable[[Settings], PoolProtocol]


class ORMPool:
    """SQLAlchemy owns pooled connections; each checkout gets its own ORM session."""

    def __init__(self, settings: Settings) -> None:
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import create_async_engine

        self.settings = settings
        url = make_url(settings.database_url).set(drivername="postgresql+psycopg")
        self.engine = create_async_engine(
            url,
            pool_size=settings.db_pool_max_size,
            max_overflow=0,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_pre_ping=True,
            connect_args={"options": "-c timezone=UTC"},
        )

    async def open(self, *, wait: bool = True) -> None:
        if wait:
            async with self.connection() as connection:
                await connection.execute("SELECT 1")

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[ORMConnection]:
        async with self.engine.connect() as connection:
            if self.settings.database_role:
                await connection.exec_driver_sql("SET ROLE promptvault_app")
                await connection.commit()
            wrapper = ORMConnection(connection)
            try:
                yield wrapper
                await wrapper.commit()
            except BaseException:
                await wrapper.rollback()
                raise
            finally:
                await wrapper.session.close()


def create_pool(settings: Settings) -> ORMPool:
    return ORMPool(settings)


def get_pool(request: Request) -> PoolProtocol:
    return cast(PoolProtocol, request.app.state.db_pool)

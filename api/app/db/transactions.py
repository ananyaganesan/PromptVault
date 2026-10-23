"""Request-scoped database transactions."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from api.app.db.orm import ORMConnection
from api.app.db.pool import PoolProtocol, get_pool
from fastapi import Depends

DatabaseConnection = ORMConnection


async def get_connection(
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> AsyncIterator[DatabaseConnection]:
    async with pool.connection() as raw_connection:
        connection = cast(ORMConnection, raw_connection)
        async with connection.transaction():
            yield connection


async def get_snapshot_connection(
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> AsyncIterator[DatabaseConnection]:
    """Read-only aggregation; auth and all dashboard reads share this snapshot."""
    async with pool.connection() as raw_connection:
        connection = cast(ORMConnection, raw_connection)
        async with connection.transaction():
            await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            yield connection

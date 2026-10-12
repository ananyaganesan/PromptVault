"""Request-scoped database transactions."""

from collections.abc import AsyncIterator
from typing import Annotated, Any, cast

from api.app.db.pool import PoolProtocol, get_pool
from fastapi import Depends
from psycopg import AsyncConnection

DatabaseConnection = AsyncConnection[dict[str, Any]]


async def get_connection(
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> AsyncIterator[DatabaseConnection]:
    async with pool.connection() as raw_connection:
        connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
        async with connection.transaction():
            yield connection


async def get_snapshot_connection(
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> AsyncIterator[DatabaseConnection]:
    """Read-only aggregation; auth and all dashboard reads share this snapshot."""
    async with pool.connection() as raw_connection:
        connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
        async with connection.transaction():
            await connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            yield connection

"""Database readiness checks."""

import asyncio

from api.app.db.pool import PoolProtocol


async def check_database(pool: PoolProtocol, timeout_seconds: float) -> None:
    async with asyncio.timeout(timeout_seconds):
        async with pool.connection() as connection:
            await connection.execute("SELECT 1")

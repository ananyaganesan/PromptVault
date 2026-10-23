"""Real ORM connections for isolated transaction/concurrency tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from api.app.config import Settings
from api.app.db.orm import ORMConnection
from api.app.db.pool import create_pool


@asynccontextmanager
async def orm_connection(database_url: str) -> AsyncIterator[ORMConnection]:
    if not urlsplit(database_url).path.endswith("_test"):
        raise RuntimeError("ORM test connections require an isolated _test database")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        secret_key="isolated-test-secret-at-least-32-characters",
    )
    pool = create_pool(settings)
    try:
        async with pool.connection() as connection:
            yield connection
    finally:
        await pool.close()

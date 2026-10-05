import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.config import Settings
from api.app.db.commands import seed_database
from api.app.db.migrations import migrate_database

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    migrate_database(url, REPOSITORY_ROOT / "db" / "migrations")
    seed_database(url, REPOSITORY_ROOT / "db" / "seeds")
    return url


@pytest.fixture
def db_connection(database_url: str) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    connection = psycopg.connect(database_url, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def isolated_database_url(database_url: str) -> str:
    with psycopg.connect(database_url, autocommit=True) as connection:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
        if not str(database_name).endswith("_test"):
            raise RuntimeError("isolated tests require a database name ending in _test")
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
    migrate_database(database_url, REPOSITORY_ROOT / "db" / "migrations")
    seed_database(database_url, REPOSITORY_ROOT / "db" / "seeds")
    return database_url


@pytest.fixture
def api_client(isolated_database_url: str) -> Iterator[TestClient]:
    os.environ.setdefault("DATABASE_URL", isolated_database_url)
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("SECRET_KEY", "test-secret-that-is-at-least-32-characters")
    from api.app.main import create_app

    settings = Settings(
        environment="test",
        database_url=isolated_database_url,
        secret_key="test-secret-that-is-at-least-32-characters",
        auth_rate_limit_requests=10_000,
        password_reset_rate_limit_requests=10_000,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        yield client

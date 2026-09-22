import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from api.app.config import Settings
from api.app.db.migrations import migrate_database

os.environ.setdefault(
    "DATABASE_URL", "postgresql://promptvault:promptvault@localhost:5432/promptvault_test"
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-that-is-long-enough")


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault_test",
        secret_key="test-secret-that-is-long-enough",
        _env_file=None,
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return url


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: str) -> str:
    migrations_directory = Path(__file__).resolve().parents[2] / "db" / "migrations"
    migrate_database(test_database_url, migrations_directory)
    return test_database_url


@pytest.fixture
def db_connection(migrated_database_url: str) -> Iterator[psycopg.Connection[Any]]:
    connection = psycopg.connect(migrated_database_url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()

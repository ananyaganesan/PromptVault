import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

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

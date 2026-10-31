import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest
from api.app.config import Settings
from api.app.db.commands import seed_database
from api.app.db.migrations import migrate_database

os.environ.setdefault(
    "DATABASE_URL", "postgresql://promptvault:promptvault@localhost:5432/promptvault_test"
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-that-is-at-least-32-characters")


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://promptvault:promptvault@localhost:5432/promptvault_test",
        ),
        secret_key="test-secret-that-is-at-least-32-characters",
        auth_rate_limit_requests=10_000,
        password_reset_rate_limit_requests=10_000,
        _env_file=None,
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not urlsplit(url).path.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must target a separate _test database")
    return url


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: str) -> str:
    migrations_directory = Path(__file__).resolve().parents[2] / "db" / "migrations"
    migrate_database(test_database_url, migrations_directory)
    return test_database_url


@pytest.fixture(scope="session")
def seeded_database_url(migrated_database_url: str) -> str:
    seeds_directory = Path(__file__).resolve().parents[2] / "db" / "seeds"
    seed_database(migrated_database_url, seeds_directory)
    return migrated_database_url


@pytest.fixture
def db_connection(migrated_database_url: str) -> Iterator[psycopg.Connection[Any]]:
    connection = psycopg.connect(migrated_database_url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def capture_project_invitation_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.invitation_support import TOKENS, capture_invitation

    TOKENS.clear()
    monkeypatch.setattr(
        "api.app.services.projects.send_project_invitation_email", capture_invitation
    )

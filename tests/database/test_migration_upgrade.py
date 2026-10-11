"""Fresh and legacy migration paths must preserve existing database rows."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from api.app.db.migrations import (
    Migration,
    apply_migrations,
    discover_migrations,
    migrate_database,
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture
def temporary_database_url(database_url: str) -> Iterator[str]:
    name = f"promptvault_upgrade_{uuid4().hex[:12]}_test"
    admin_url = make_conninfo(database_url, dbname="postgres")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(database_url, dbname=name)
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def assert_preserved_rows_and_fk(url: str, user_id: str, token_hash: str) -> None:
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone() == (22,)
        assert connection.execute(
            "SELECT email FROM users WHERE id = %s", (user_id,)
        ).fetchone() == ("migration-check@example.com",)
        assert connection.execute(
            "SELECT token_hash FROM password_reset_tokens WHERE user_id = %s", (user_id,)
        ).fetchone() == (token_hash,)
        foreign_keys = set(
            connection.execute(
                "SELECT conrelid::regclass::text, confrelid::regclass::text "
                "FROM pg_constraint WHERE contype = 'f'"
            ).fetchall()
        )
        assert {
            ("project_members", "projects"),
            ("project_members", "users"),
            ("prompts", "projects"),
            ("prompt_versions", "prompts"),
            ("password_reset_tokens", "users"),
            ("password_history", "users"),
            ("run_reservations", "users"),
            ("run_reservations", "projects"),
            ("run_reservations", "prompts"),
            ("run_reservations", "prompt_versions"),
            ("auth_sessions", "users"),
        } <= foreign_keys


def insert_existing_rows(url: str) -> tuple[str, str]:
    user_id = str(uuid4())
    token_hash = "a" * 64
    with psycopg.connect(url) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) VALUES (%s, %s, %s, %s)",
            (user_id, "migration-check@example.com", "Migration Check", "unused"),
        )
        connection.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, now() + interval '1 hour')",
            (user_id, token_hash),
        )
    return user_id, token_hash


def test_fresh_migrations_are_idempotent_and_preserve_rows(temporary_database_url: str) -> None:
    assert len(migrate_database(temporary_database_url, MIGRATIONS)) == 22
    user_id, token_hash = insert_existing_rows(temporary_database_url)

    assert migrate_database(temporary_database_url, MIGRATIONS) == []
    assert_preserved_rows_and_fk(temporary_database_url, user_id, token_hash)


def test_legacy_password_reset_history_upgrades_without_resetting_data(
    temporary_database_url: str,
) -> None:
    migrations = discover_migrations(MIGRATIONS)
    reset = next(item for item in migrations if item.version == 15)
    legacy = Migration(
        version=11, name=reset.name, path=reset.path, checksum=reset.checksum, sql=reset.sql
    )
    with psycopg.connect(temporary_database_url, autocommit=True) as connection:
        apply_migrations(connection, [*migrations[:10], legacy])
    user_id, token_hash = insert_existing_rows(temporary_database_url)

    applied = migrate_database(temporary_database_url, MIGRATIONS)

    assert [item.version for item in applied] == [
        11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22
    ]
    assert_preserved_rows_and_fk(temporary_database_url, user_id, token_hash)
    with psycopg.connect(temporary_database_url) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = 15"
        ).fetchone() == (reset.checksum,)
        assert connection.execute(
            "SELECT password_hash FROM password_history WHERE user_id = %s", (user_id,)
        ).fetchone() == ("unused",)

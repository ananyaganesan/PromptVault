"""Ordered, checksummed PostgreSQL migration execution."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

import psycopg

_MIGRATION_FILENAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
_LOCK_SQL = "SELECT pg_advisory_lock(hashtext('promptvault_migrations'))"
_UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtext('promptvault_migrations'))"
_CREATE_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_SELECT_APPLIED_SQL = """
SELECT version, name, checksum
FROM schema_migrations
ORDER BY version
"""
_INSERT_APPLIED_SQL = """
INSERT INTO schema_migrations (version, name, checksum)
VALUES (%s, %s, %s)
"""
_RECORD_LEGACY_PASSWORD_RESET_SQL = """
UPDATE schema_migrations
SET version = %s
WHERE version = %s
  AND name = %s
  AND checksum = %s
  AND to_regclass('public.password_reset_tokens') IS NOT NULL
"""
_LEGACY_PASSWORD_RESET_VERSION = 11
_PASSWORD_RESET_VERSION = 15
_PASSWORD_RESET_NAME = "password_reset_tokens"


class MigrationError(RuntimeError):
    """Raised when migration files or recorded history are unsafe."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: int
    name: str
    checksum: str


class ResultLike(Protocol):
    def fetchall(self) -> list[tuple[int, str, str]]: ...


class ConnectionLike(Protocol):
    def execute(
        self,
        query: str,
        params: tuple[object, ...] | None = None,
    ) -> ResultLike: ...

    def transaction(self) -> AbstractContextManager[object]: ...


def discover_migrations(directory: Path) -> list[Migration]:
    if not directory.is_dir():
        raise MigrationError(f"migration directory does not exist: {directory}")

    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in seen_versions:
            raise MigrationError(f"duplicate migration version {version}")
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise MigrationError(f"migration is empty: {path.name}")
        seen_versions.add(version)
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=sha256(path.read_bytes()).hexdigest(),
                sql=sql,
            )
        )
    return sorted(migrations, key=lambda migration: migration.version)


def plan_migrations(
    migrations: Sequence[Migration],
    applied: dict[int, AppliedMigration],
) -> list[Migration]:
    available = {migration.version: migration for migration in migrations}
    for version, recorded in applied.items():
        migration = available.get(version)
        if migration is None:
            raise MigrationError(f"applied migration {version} is missing from the directory")
        if recorded.name != migration.name:
            raise MigrationError(f"applied migration {version} name changed")
        if recorded.checksum != migration.checksum:
            raise MigrationError(f"applied migration {version} checksum changed")
    return [migration for migration in migrations if migration.version not in applied]


def _read_applied(connection: ConnectionLike) -> dict[int, AppliedMigration]:
    rows = connection.execute(_SELECT_APPLIED_SQL).fetchall()
    return {
        int(version): AppliedMigration(
            version=int(version),
            name=str(name),
            checksum=str(checksum),
        )
        for version, name, checksum in rows
    }


def _reconcile_legacy_password_reset(
    connection: ConnectionLike,
    migrations: Sequence[Migration],
    applied: dict[int, AppliedMigration],
) -> dict[int, AppliedMigration]:
    """Move the exact misnumbered reset record to 015 without rerunning its DDL."""

    legacy = applied.get(_LEGACY_PASSWORD_RESET_VERSION)
    if legacy is None or legacy.name != _PASSWORD_RESET_NAME:
        return applied

    current = next(
        (item for item in migrations if item.version == _PASSWORD_RESET_VERSION),
        None,
    )
    if current is None or current.name != _PASSWORD_RESET_NAME:
        raise MigrationError("password-reset migration 015 is missing")
    run_budget = next(
        (item for item in migrations if item.version == _LEGACY_PASSWORD_RESET_VERSION),
        None,
    )
    if run_budget is None or run_budget.name != "run_budget_boundary":
        raise MigrationError("run-budget migration 011 is missing")
    if legacy.checksum != current.checksum:
        raise MigrationError("legacy password-reset migration checksum changed")
    if _PASSWORD_RESET_VERSION in applied:
        raise MigrationError("both legacy and current password-reset migrations are recorded")

    with connection.transaction():
        connection.execute(
            _RECORD_LEGACY_PASSWORD_RESET_SQL,
            (
                _PASSWORD_RESET_VERSION,
                _LEGACY_PASSWORD_RESET_VERSION,
                _PASSWORD_RESET_NAME,
                legacy.checksum,
            ),
        )
    reconciled = _read_applied(connection)
    if _LEGACY_PASSWORD_RESET_VERSION in reconciled:
        raise MigrationError(
            "legacy password-reset table is missing; migration history was not changed"
        )
    return reconciled


def apply_migrations(
    connection: ConnectionLike,
    migrations: Iterable[Migration],
) -> list[Migration]:
    ordered = sorted(migrations, key=lambda migration: migration.version)
    connection.execute(_LOCK_SQL)
    try:
        with connection.transaction():
            connection.execute(_CREATE_TRACKING_TABLE_SQL)
        applied = _reconcile_legacy_password_reset(connection, ordered, _read_applied(connection))
        pending = plan_migrations(ordered, applied)
        for migration in pending:
            with connection.transaction():
                connection.execute(migration.sql)
                connection.execute(
                    _INSERT_APPLIED_SQL,
                    (migration.version, migration.name, migration.checksum),
                )
        return pending
    finally:
        connection.execute(_UNLOCK_SQL)


def migrate_database(database_url: str, directory: Path) -> list[Migration]:
    migrations = discover_migrations(directory)
    with psycopg.connect(database_url, autocommit=True) as connection:
        return apply_migrations(connection, migrations)

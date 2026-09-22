from __future__ import annotations

from contextlib import AbstractContextManager
from hashlib import sha256
from pathlib import Path
from types import TracebackType

import api.app.db.migrations as migrations_module
import pytest
from api.app.db.migrations import (
    AppliedMigration,
    MigrationError,
    apply_migrations,
    discover_migrations,
    plan_migrations,
)


def write_migration(directory: Path, name: str, sql: str) -> Path:
    path = directory / name
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_migrations_orders_versions_and_hashes_content(tmp_path: Path) -> None:
    second = write_migration(tmp_path, "002_tables.sql", "CREATE TABLE example(id int);\n")
    first = write_migration(tmp_path, "001_extensions.sql", "CREATE EXTENSION pgcrypto;\n")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2]
    assert [migration.name for migration in migrations] == ["extensions", "tables"]
    assert migrations[0].checksum == sha256(first.read_bytes()).hexdigest()
    assert migrations[1].path == second


def test_discover_migrations_rejects_duplicate_version(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 1;\n")
    write_migration(tmp_path, "001_tables.sql", "SELECT 2;\n")

    with pytest.raises(MigrationError, match="duplicate migration version 1"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_empty_sql(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_empty.sql", "  \n")

    with pytest.raises(MigrationError, match="migration is empty"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_invalid_filename(tmp_path: Path) -> None:
    write_migration(tmp_path, "create_tables.sql", "SELECT 1;\n")

    with pytest.raises(MigrationError, match="invalid migration filename"):
        discover_migrations(tmp_path)


def test_plan_migrations_rejects_changed_applied_checksum(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 1;\n")
    migration = discover_migrations(tmp_path)[0]
    applied = {
        1: AppliedMigration(version=1, name="extensions", checksum="0" * 64),
    }

    with pytest.raises(MigrationError, match="checksum changed"):
        plan_migrations([migration], applied)


def test_plan_migrations_rejects_applied_version_missing_from_directory(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 1;\n")
    migrations = discover_migrations(tmp_path)
    applied = {2: AppliedMigration(version=2, name="tables", checksum="0" * 64)}

    with pytest.raises(MigrationError, match="applied migration 2 is missing"):
        plan_migrations(migrations, applied)


def test_plan_migrations_returns_only_pending_versions(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 1;\n")
    write_migration(tmp_path, "002_tables.sql", "SELECT 2;\n")
    migrations = discover_migrations(tmp_path)
    applied = {
        1: AppliedMigration(
            version=1,
            name="extensions",
            checksum=migrations[0].checksum,
        )
    }

    assert plan_migrations(migrations, applied) == [migrations[1]]


class FakeResult:
    def __init__(self, rows: list[tuple[int, str, str]] | None = None) -> None:
        self.rows = rows or []

    def fetchall(self) -> list[tuple[int, str, str]]:
        return self.rows


class FakeTransaction(AbstractContextManager[None]):
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> None:
        self.connection.events.append("begin")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.connection.events.append("rollback" if exc_type else "commit")


class FakeConnection:
    def __init__(self) -> None:
        self.applied: list[tuple[int, str, str]] = []
        self.events: list[str] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> FakeResult:
        normalized = " ".join(query.split())
        if "pg_advisory_lock" in normalized:
            self.events.append("lock")
        elif "pg_advisory_unlock" in normalized:
            self.events.append("unlock")
        elif normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            self.events.append("tracking-table")
        elif normalized.startswith("SELECT version, name, checksum"):
            return FakeResult(self.applied.copy())
        elif normalized.startswith("INSERT INTO schema_migrations"):
            assert params is not None
            row = (int(params[0]), str(params[1]), str(params[2]))
            self.applied.append(row)
            self.events.append(f"track:{row[0]}")
        else:
            self.events.append(f"sql:{normalized}")
        return FakeResult()


class FakeConnectionContext(FakeConnection):
    def __enter__(self) -> FakeConnectionContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_apply_migrations_tracks_each_file_transactionally(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 'first';\n")
    write_migration(tmp_path, "002_tables.sql", "SELECT 'second';\n")
    connection = FakeConnection()

    applied = apply_migrations(connection, discover_migrations(tmp_path))

    assert [migration.version for migration in applied] == [1, 2]
    assert connection.events == [
        "lock",
        "begin",
        "tracking-table",
        "commit",
        "begin",
        "sql:SELECT 'first';",
        "track:1",
        "commit",
        "begin",
        "sql:SELECT 'second';",
        "track:2",
        "commit",
        "unlock",
    ]


def test_migrate_database_uses_autocommit_for_real_transaction_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_migration(tmp_path, "001_extensions.sql", "SELECT 1;\n")
    connection = FakeConnectionContext()
    connect_options: dict[str, object] = {}

    def fake_connect(url: str, *, autocommit: bool = False) -> FakeConnectionContext:
        connect_options.update(url=url, autocommit=autocommit)
        return connection

    monkeypatch.setattr(migrations_module.psycopg, "connect", fake_connect)

    migrations_module.migrate_database("postgresql://test", tmp_path)

    assert connect_options == {"url": "postgresql://test", "autocommit": True}

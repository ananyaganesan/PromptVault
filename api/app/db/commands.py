"""Safe database seed and development-reset operations."""

from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psycopg
from api.app.db.migrations import apply_migrations, discover_migrations


class DatabaseCommandError(RuntimeError):
    """Raised when a database command cannot safely proceed."""


class ResetRefusedError(DatabaseCommandError):
    """Raised when development-reset safeguards are not satisfied."""


class SeedRefusedError(DatabaseCommandError):
    """Raised when development seed data is requested outside a safe environment."""


@dataclass(frozen=True, slots=True)
class SeedFile:
    path: Path
    sql: str


class SeedConnectionLike(Protocol):
    def execute(self, query: str, params: tuple[object, ...] | None = None) -> object: ...

    def transaction(self) -> AbstractContextManager[object]: ...


def discover_seed_files(directory: Path) -> list[SeedFile]:
    if not directory.is_dir():
        raise DatabaseCommandError(f"seed directory does not exist: {directory}")
    seeds: list[SeedFile] = []
    for path in sorted(directory.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise DatabaseCommandError(f"seed file is empty: {path.name}")
        seeds.append(SeedFile(path=path, sql=sql))
    return seeds


def apply_seed_files(connection: SeedConnectionLike, seeds: Iterable[SeedFile]) -> None:
    with connection.transaction():
        for seed in seeds:
            connection.execute(seed.sql)


def require_development_reset(*, environment: str, confirmed: bool) -> None:
    if environment != "development":
        raise ResetRefusedError("reset is allowed only in the development environment")
    if not confirmed:
        raise ResetRefusedError("reset requires explicit confirmation")


def require_development_seed(*, environment: str) -> None:
    if environment not in {"development", "test"}:
        raise SeedRefusedError("development seeds are allowed only in development or test")


def database_url(explicit: str | None = None) -> str:
    value = explicit or os.getenv("DATABASE_URL")
    if not value:
        raise DatabaseCommandError("DATABASE_URL is required")
    return value


def seed_database(url: str, seeds_directory: Path) -> list[SeedFile]:
    require_development_seed(environment=os.getenv("ENVIRONMENT", "development"))
    seeds = discover_seed_files(seeds_directory)
    with psycopg.connect(url) as connection:
        apply_seed_files(connection, seeds)
    return seeds


def reset_development_database(
    url: str,
    *,
    environment: str,
    confirmed: bool,
    migrations_directory: Path,
    seeds_directory: Path,
) -> tuple[int, int]:
    require_development_reset(environment=environment, confirmed=confirmed)
    migrations = discover_migrations(migrations_directory)
    seeds = discover_seed_files(seeds_directory)
    with psycopg.connect(url) as connection, connection.transaction():
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
        applied = apply_migrations(connection, migrations)
        apply_seed_files(connection, seeds)
    return len(applied), len(seeds)

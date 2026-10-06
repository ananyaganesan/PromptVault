from __future__ import annotations

import subprocess
import sys
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

import pytest
from api.app.db.commands import (
    DatabaseCommandError,
    ResetRefusedError,
    SeedRefusedError,
    apply_seed_files,
    discover_seed_files,
    require_development_reset,
    require_development_seed,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
        self.events: list[str] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> object:
        assert params is None
        self.events.append(f"sql:{' '.join(query.split())}")
        return object()


def test_discover_seed_files_rejects_empty_file(tmp_path: Path) -> None:
    (tmp_path / "demo.sql").write_text("\n", encoding="utf-8")

    with pytest.raises(DatabaseCommandError, match="seed file is empty"):
        discover_seed_files(tmp_path)


def test_apply_seed_files_executes_all_files_in_one_transaction(tmp_path: Path) -> None:
    first = tmp_path / "01-base.sql"
    second = tmp_path / "02-demo.sql"
    first.write_text("SELECT 'base';\n", encoding="utf-8")
    second.write_text("SELECT 'demo';\n", encoding="utf-8")
    connection = FakeConnection()

    apply_seed_files(connection, discover_seed_files(tmp_path))

    assert connection.events == [
        "begin",
        "sql:SELECT 'base';",
        "sql:SELECT 'demo';",
        "commit",
    ]


@pytest.mark.parametrize(
    ("environment", "confirmed", "message"),
    [
        ("production", True, "development environment"),
        ("development", False, "explicit confirmation"),
    ],
)
def test_reset_requires_development_and_confirmation(
    environment: str,
    confirmed: bool,
    message: str,
) -> None:
    with pytest.raises(ResetRefusedError, match=message):
        require_development_reset(environment=environment, confirmed=confirmed)


def test_reset_allows_confirmed_development() -> None:
    require_development_reset(environment="development", confirmed=True)


def test_development_seeds_are_refused_in_production() -> None:
    with pytest.raises(SeedRefusedError, match="development or test"):
        require_development_seed(environment="production")


@pytest.mark.parametrize(
    "script",
    [
        "run-migrations.py",
        "seed-database.py",
        "reset-development.py",
        "create-partition.py",
        "refresh-views.py",
    ],
)
def test_database_script_exposes_help(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / script), "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()

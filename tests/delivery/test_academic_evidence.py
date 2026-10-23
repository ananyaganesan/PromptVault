"""Academic evidence checks must execute SQL and preserve the selected database."""

import json
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "collect-academic-evidence.py"


def test_academic_collector_refuses_non_test_database(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            "postgresql://localhost/promptvault",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Requires disposable _test database" in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.database
def test_academic_collector_proves_invariants_without_retaining_writes(
    database_url: str,
    tmp_path: Path,
) -> None:
    def counts() -> tuple[int, ...]:
        with psycopg.connect(database_url) as connection:
            return tuple(
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in (
                    "projects",
                    "project_members",
                    "runs",
                    "audit_events",
                    "auth_sessions",
                    "password_reset_tokens",
                    "run_reservations",
                )
            )

    before = counts()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            database_url,
            "--output-dir",
            str(tmp_path),
            "--dictionary",
            str(tmp_path / "dictionary.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert counts() == before
    report = json.loads((tmp_path / "database-evidence.json").read_text())
    assert report["logical_tables"] == 24
    assert len(report["migrations"]) == 31
    assert report["demonstrations"]["owner_membership_trigger"] == 1
    assert report["demonstrations"]["invalid_foreign_key"] == "23503 rejected"
    assert {row["action"] for row in report["demonstrations"]["audit_trigger"]} == {
        "insert",
        "update",
        "delete",
    }
    history = next(
        table for table in report["tables"] if table["name"] == "password_history"
    )
    assert next(
        row["definition"] for row in history["constraints"] if row["kind"] == "p"
    ) == ("PRIMARY KEY (id)")
    assert report["joins"] and report["aggregates"] and report["view_samples"]
    dictionary = (tmp_path / "dictionary.md").read_text()
    assert "Argon2id" in dictionary
    assert "encrypted_secret" in dictionary

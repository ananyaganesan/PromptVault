#!/usr/bin/env python3
"""Apply ordered PromptVault database migrations."""

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import DatabaseCommandError, database_url
from api.app.db.migrations import MigrationError, migrate_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=REPOSITORY_ROOT / "db" / "migrations",
    )
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        applied = migrate_database(database_url(args.database_url), args.migrations_dir)
    except (DatabaseCommandError, MigrationError, OSError, psycopg.Error) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    if applied:
        print("Applied migrations: " + ", ".join(path.path.name for path in applied))
    else:
        print("Database is already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

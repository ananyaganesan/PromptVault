#!/usr/bin/env python3
"""Destructively reset only a confirmed development database."""

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import (
    DatabaseCommandError,
    database_url,
    reset_development_database,
)
from api.app.db.migrations import MigrationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--environment", choices=["development", "test", "production"])
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Confirm that all data in the development database may be deleted",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=REPOSITORY_ROOT / "db" / "migrations",
    )
    parser.add_argument(
        "--seeds-dir",
        type=Path,
        default=REPOSITORY_ROOT / "db" / "seeds",
    )
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        migration_count, seed_count = reset_development_database(
            database_url(args.database_url),
            environment=args.environment or os.getenv("ENVIRONMENT", "development"),
            confirmed=args.confirm_reset,
            migrations_directory=args.migrations_dir,
            seeds_directory=args.seeds_dir,
        )
    except (DatabaseCommandError, MigrationError, OSError, psycopg.Error) as exc:
        print(f"Reset refused or failed: {exc}", file=sys.stderr)
        return 1
    print(f"Reset complete: {migration_count} migration(s), {seed_count} seed file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

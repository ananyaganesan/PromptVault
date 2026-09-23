#!/usr/bin/env python3
"""Apply idempotent PromptVault seed SQL files."""

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import (
    DatabaseCommandError,
    database_url,
    seed_database,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
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
        applied = seed_database(database_url(args.database_url), args.seeds_dir)
    except (DatabaseCommandError, OSError, psycopg.Error) as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1
    print(f"Applied {len(applied)} seed file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

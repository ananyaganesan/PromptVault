#!/usr/bin/env python3
"""Seed a deterministic representative run ledger for local performance checks."""

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import DatabaseCommandError, database_url
from api.app.db.representative_data import seed_representative_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--runs", type=int, default=2_000, help="Number of ledger rows")
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        summary = seed_representative_dataset(
            database_url(args.database_url), run_count=args.runs
        )
    except (DatabaseCommandError, OSError, RuntimeError, ValueError, psycopg.Error) as exc:
        print(f"Representative data seed failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Representative dataset ready: {summary['run_count']} runs "
        f"in {summary['partition']} for project {summary['project_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create an idempotent monthly run partition."""

import argparse
import sys
from datetime import date
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import DatabaseCommandError, database_url


def month_value(raw: str) -> date:
    try:
        return date.fromisoformat(f"{raw}-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("month must use YYYY-MM") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("month", nargs="?", type=month_value, help="Target month YYYY-MM")
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    target = args.month
    try:
        with psycopg.connect(database_url(args.database_url)) as connection:
            if target is None:
                target = connection.execute(
                    "SELECT (date_trunc('month', current_date) + INTERVAL '1 month')::date"
                ).fetchone()[0]
            partition = connection.execute(
                "SELECT create_run_partition(%s)", (target,)
            ).fetchone()[0]
    except (DatabaseCommandError, psycopg.Error) as exc:
        print(f"Partition creation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Partition ready: {partition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

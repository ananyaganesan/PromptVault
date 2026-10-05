#!/usr/bin/env python3
"""Refresh PromptVault reporting materialized views."""

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import DatabaseCommandError, database_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        with psycopg.connect(
            database_url(args.database_url), autocommit=True
        ) as connection:
            connection.execute(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY organization_monthly_metrics"
            )
            connection.execute(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY user_monthly_metrics"
            )
    except (DatabaseCommandError, psycopg.Error) as exc:
        print(f"View refresh failed: {exc}", file=sys.stderr)
        return 1
    print("Refreshed organization_monthly_metrics and user_monthly_metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recover interrupted work and perform scheduled database maintenance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv

from api.app.db.commands import DatabaseCommandError, database_url


def positive_minutes(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("minutes must be positive")
    return value


def positive_days(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("days must be positive")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Owner database URL override")
    parser.add_argument("--stale-reservation-minutes", type=positive_minutes, default=10)
    parser.add_argument("--security-retention-days", type=positive_days, default=30)
    parser.add_argument("--idempotency-retention-days", type=positive_days, default=30)
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        with psycopg.connect(database_url(args.database_url)) as connection:
            connection.execute(
                "CALL perform_system_maintenance(%s::interval, %s::interval, %s::interval)",
                (
                    f"{args.stale_reservation_minutes} minutes",
                    f"{args.security_retention_days} days",
                    f"{args.idempotency_retention_days} days",
                ),
            )
    except (DatabaseCommandError, psycopg.Error) as exc:
        print(f"Maintenance failed: {exc}", file=sys.stderr)
        return 1
    print("Maintenance completed: recovery, cleanup, partition, and analytics refresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

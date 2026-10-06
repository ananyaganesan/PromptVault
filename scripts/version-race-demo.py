#!/usr/bin/env python3
"""Demonstrate collision-free prompt version allocation under concurrency."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from api.app.db.commands import DatabaseCommandError, database_url


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--workers", type=positive_integer, default=20)
    return parser


def run_race(url: str, workers: int) -> list[int]:
    user_id = uuid4()
    project_id = uuid4()
    prompt_id = uuid4()
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (%s, %s, 'Version Race Demo', 'unused')",
            (user_id, f"version-race-{user_id}@example.com"),
        )
        connection.execute(
            "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Version Race', %s, %s)",
            (project_id, f"version-race-{project_id.hex}", user_id),
        )
        connection.execute(
            "INSERT INTO prompts (id, project_id, key, name) "
            "VALUES (%s, %s, 'race-prompt', 'Race Prompt')",
            (prompt_id, project_id),
        )
        initial = connection.execute(
            """
            SELECT * FROM create_prompt_version(
                %s, NULL, 'Initial {{value}}', '["value"]'::jsonb,
                '{"provider":"mock","model":"deterministic-v1",'
                '"temperature":0,"max_output_tokens":100}'::jsonb,
                'Initial version', %s
            )
            """,
            (prompt_id, user_id),
        ).fetchone()
    if initial is None:
        raise RuntimeError("the initial version was not created")

    def save_version(index: int) -> int:
        with psycopg.connect(url, autocommit=True, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT * FROM create_prompt_version(
                    %s, %s, %s, '["value"]'::jsonb,
                    '{"provider":"mock","model":"deterministic-v1",'
                    '"temperature":0,"max_output_tokens":100}'::jsonb,
                    %s, %s
                )
                """,
                (
                    prompt_id,
                    initial["id"],
                    f"Concurrent {{{{value}}}} save {index}",
                    f"Concurrent save {index}",
                    user_id,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"concurrent save {index} returned no version")
        return int(row["version_number"])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return sorted(executor.map(save_version, range(workers)))


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        numbers = run_race(database_url(args.database_url), args.workers)
    except (DatabaseCommandError, OSError, RuntimeError, psycopg.Error) as exc:
        print(f"Version race demo failed: {exc}", file=sys.stderr)
        return 1
    expected = list(range(2, args.workers + 2))
    if numbers != expected:
        print(
            f"Version race demo failed: expected {expected}, received {numbers}",
            file=sys.stderr,
        )
        return 1
    print(f"Concurrent version saves: {args.workers}")
    print("Assigned versions: " + ", ".join(str(number) for number in numbers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

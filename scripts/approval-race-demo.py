#!/usr/bin/env python3
"""Demonstrate that only one competing production review can succeed."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv
from psycopg.errors import SerializationFailure

from api.app.db.commands import DatabaseCommandError, database_url

ADMIN_ID = UUID("22222222-2222-4222-8222-222222222222")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    return parser


def create_pending_deployment(url: str) -> UUID:
    user_id = uuid4()
    project_id = uuid4()
    prompt_id = uuid4()
    version_id = uuid4()
    with psycopg.connect(url) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (%s, %s, 'Approval Race Demo', 'unused')",
            (user_id, f"approval-race-{user_id}@example.com"),
        )
        connection.execute(
            "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Approval Race', %s, %s)",
            (project_id, f"approval-race-{project_id.hex}", user_id),
        )
        connection.execute(
            "INSERT INTO prompts (id, project_id, key, name) "
            "VALUES (%s, %s, 'approval-race', 'Approval Race')",
            (prompt_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            ) VALUES (
                %s, %s, 1, 'Approval race', '[]',
                '{"provider":"mock","model":"deterministic-v1",'
                '"temperature":0,"max_output_tokens":10}',
                'Initial version', %s
            )
            """,
            (version_id, prompt_id, user_id),
        )
        row = connection.execute(
            "SELECT (request_deployment(%s, 'prod', %s, NULL)).id",
            (version_id, user_id),
        ).fetchone()
    if row is None:
        raise RuntimeError("the pending deployment was not created")
    return UUID(str(row[0]))


def run_race(url: str) -> list[str]:
    deployment_id = create_pending_deployment(url)
    barrier = Barrier(2)

    def review(approve: bool) -> str:
        try:
            with psycopg.connect(url) as connection:
                barrier.wait()
                row = connection.execute(
                    "SELECT (review_production_deployment(%s, %s, %s, %s)).status",
                    (deployment_id, ADMIN_ID, approve, "approval race demo"),
                ).fetchone()
                if row is None:
                    raise RuntimeError("the review returned no deployment")
                return str(row[0])
        except SerializationFailure:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(review, (True, False)))


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        results = run_race(database_url(args.database_url))
    except (DatabaseCommandError, OSError, RuntimeError, psycopg.Error) as exc:
        print(f"Approval race demo failed: {exc}", file=sys.stderr)
        return 1
    successes = sum(result in {"active", "rejected"} for result in results)
    conflicts = results.count("conflict")
    print(f"Successful decisions: {successes}")
    print(f"Conflicting decisions: {conflicts}")
    print("Winning status: " + next(result for result in results if result != "conflict"))
    return 0 if successes == 1 and conflicts == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())

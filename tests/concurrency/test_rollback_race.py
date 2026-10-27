"""Concurrent rollback requests serialize on the prompt and active deployment."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation

from tests.release_support import seed_release_evidence

ADMIN_ID = UUID("22222222-2222-4222-8222-222222222222")


def create_active_third_version(database_url: str) -> tuple[UUID, UUID]:
    user_id, project_id, prompt_id = uuid4(), uuid4(), uuid4()
    versions = [uuid4(), uuid4(), uuid4()]
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) VALUES (%s, %s, 'Rollback Racer', 'unused')",
            (user_id, f"rollback-{user_id}@example.com"),
        )
        connection.execute(
            "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Rollback Race', %s, %s)",
            (project_id, f"rollback-{project_id.hex}", user_id),
        )
        connection.execute(
            "INSERT INTO prompts (id, project_id, key, name) VALUES (%s, %s, 'rollback', 'Rollback')",
            (prompt_id, project_id),
        )
        for index, version_id in enumerate(versions, start=1):
            connection.execute(
                "\n                INSERT INTO prompt_versions (id, prompt_id, version_number, template_body, provider, model, temperature, max_output_tokens, commit_message, created_by) VALUES (%s, %s, %s, %s, (%s)::jsonb->>'provider', (%s)::jsonb->>'model', ((%s)::jsonb->>'temperature')::numeric, ((%s)::jsonb->>'max_output_tokens')::integer, %s, %s)\n                ",
                (
                    version_id,
                    prompt_id,
                    index,
                    f"Version {index}",
                    '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":10}',
                    '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":10}',
                    '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":10}',
                    '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":10}',
                    f"Version {index}",
                    user_id,
                ),
            )
        validation_id = seed_release_evidence(connection, versions[2], user_id)
        pending_id = connection.execute(
            "SELECT (request_deployment(%s, 'prod', %s, NULL, %s)).id",
            (versions[2], user_id, validation_id),
        ).fetchone()[0]
        connection.execute(
            "SELECT review_production_deployment(%s, %s, TRUE, 'approved')",
            (pending_id, ADMIN_ID),
        )
    return prompt_id, versions[1]


@pytest.mark.database
def test_same_target_rollbacks_have_exactly_one_winner(database_url: str) -> None:
    prompt_id, target_version_id = create_active_third_version(database_url)
    barrier = Barrier(2)

    def rollback() -> str:
        try:
            with psycopg.connect(database_url) as connection:
                barrier.wait()
                return str(
                    connection.execute(
                        "SELECT (rollback_deployment(%s, %s, %s, 'race', 'prod')).status",
                        (prompt_id, target_version_id, ADMIN_ID),
                    ).fetchone()[0]
                )
        except CheckViolation:
            return "invalid_rollback_target"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rollback(), range(2)))

    assert sorted(results) == ["active", "invalid_rollback_target"]
    with psycopg.connect(database_url) as connection:
        active = connection.execute(
            """
            SELECT version_id FROM deployment_context
            WHERE prompt_id = %s AND environment = 'prod' AND status = 'active'
            """,
            (prompt_id,),
        ).fetchall()
        rollback_count = connection.execute(
            "SELECT count(*) FROM deployment_context WHERE prompt_id = %s AND rollback_of_id IS NOT NULL",
            (prompt_id,),
        ).fetchone()[0]
    assert active == [(target_version_id,)]
    assert rollback_count == 1

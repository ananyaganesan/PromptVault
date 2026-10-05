from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import SerializationFailure

ADMIN_ID = UUID("22222222-2222-4222-8222-222222222222")


def create_pending_deployment(database_url: str, label: str) -> tuple[UUID, UUID]:
    user_id = uuid4()
    project_id = uuid4()
    prompt_id = uuid4()
    version_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (%s, %s, 'Approval Racer', 'unused')",
            (user_id, f"{label}-{user_id}@example.com"),
        )
        connection.execute(
            "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Race', %s, %s)",
            (project_id, f"{label}-{project_id.hex}", user_id),
        )
        connection.execute(
            "INSERT INTO prompts (id, project_id, key, name) "
            "VALUES (%s, %s, 'approval', 'Approval')",
            (prompt_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            ) VALUES (
                %s, %s, 1, 'Approval', '[]',
                '{"provider":"mock","model":"deterministic-v1",'
                '"temperature":0,"max_output_tokens":10}',
                'Initial', %s
            )
            """,
            (version_id, prompt_id, user_id),
        )
        deployment_id = connection.execute(
            "SELECT (request_deployment(%s, 'prod', %s, NULL)).id",
            (version_id, user_id),
        ).fetchone()[0]
    return deployment_id, user_id


@pytest.mark.database
def test_two_competing_production_reviews_have_exactly_one_winner(
    database_url: str,
) -> None:
    deployment_id, _ = create_pending_deployment(database_url, "approval")

    barrier = Barrier(2)

    def review(approve: bool) -> str:
        try:
            with psycopg.connect(database_url) as connection:
                barrier.wait()
                row = connection.execute(
                    "SELECT (review_production_deployment(%s, %s, %s, %s)).status",
                    (deployment_id, ADMIN_ID, approve, "reviewed"),
                ).fetchone()
                assert row is not None
                return str(row[0])
        except SerializationFailure:
            return "already_reviewed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(review, (True, False)))

    assert results.count("already_reviewed") == 1
    assert sum(result in {"active", "rejected"} for result in results) == 1
    with psycopg.connect(database_url) as connection:
        final_status = connection.execute(
            "SELECT status FROM deployments WHERE id = %s", (deployment_id,)
        ).fetchone()[0]
    assert final_status in {"active", "rejected"}


@pytest.mark.database
def test_cancellation_and_review_cannot_both_win(database_url: str) -> None:
    deployment_id, requester_id = create_pending_deployment(database_url, "cancel-review")
    barrier = Barrier(2)

    def cancel() -> str:
        with psycopg.connect(database_url) as connection:
            barrier.wait()
            row = connection.execute(
                """UPDATE deployments SET status = 'cancelled'
                   WHERE id = %s AND requested_by = %s AND status = 'pending'
                   RETURNING status""",
                (deployment_id, requester_id),
            ).fetchone()
            return str(row[0]) if row else "lost"

    def approve() -> str:
        try:
            with psycopg.connect(database_url) as connection:
                barrier.wait()
                row = connection.execute(
                    "SELECT (review_production_deployment(%s, %s, TRUE, NULL)).status",
                    (deployment_id, ADMIN_ID),
                ).fetchone()
                assert row is not None
                return str(row[0])
        except SerializationFailure:
            return "lost"

    with ThreadPoolExecutor(max_workers=2) as executor:
        cancellation = executor.submit(cancel)
        approval = executor.submit(approve)
        results = [cancellation.result(), approval.result()]

    assert results.count("lost") == 1
    assert sum(result in {"cancelled", "active"} for result in results) == 1

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest


@pytest.mark.database
def test_concurrent_admission_never_reserves_more_than_user_budget(
    database_url: str,
) -> None:
    user_id, project_id, prompt_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (%s, %s, 'Reservation Racer', 'unused')",
            (user_id, f"reservation-race-{user_id}@example.com"),
        )
        connection.execute(
            "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Race', %s, %s)",
            (project_id, f"reservation-race-{project_id.hex}", user_id),
        )
        connection.execute(
            "INSERT INTO prompts (id, project_id, key, name) "
            "VALUES (%s, %s, 'race', 'Race')",
            (prompt_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            ) VALUES (
                %s, %s, 1, 'Race', '[]',
                '{"provider":"gemini","model":"gemini-2.5-flash",'
                '"temperature":0,"max_output_tokens":100}',
                'Initial', %s
            )
            """,
            (version_id, prompt_id, user_id),
        )
        connection.execute(
            "INSERT INTO budgets (user_id, monthly_limit) VALUES (%s, 1)",
            (user_id,),
        )

    workers = 12
    barrier = Barrier(workers)

    def reserve(index: int) -> str:
        with psycopg.connect(database_url) as connection:
            barrier.wait()
            row = connection.execute(
                """
                SELECT reserved.status FROM reserve_run_execution(
                    p_user_id => %s, p_project_id => %s,
                    p_prompt_id => %s, p_version_id => %s,
                    p_idempotency_key => %s, p_request_fingerprint => %s,
                    p_claim_token => %s, p_estimated_cost => 0.25,
                    p_maximum_concurrent => 20
                ) AS reserved
                """,
                (
                    user_id,
                    project_id,
                    prompt_id,
                    version_id,
                    f"reservation-race-{index:04d}",
                    f"{index:064x}",
                    uuid4(),
                ),
            ).fetchone()
            assert row is not None
            return row[0]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        statuses = list(executor.map(reserve, range(workers)))

    assert statuses.count("reserved") == 4
    assert statuses.count("blocked") == workers - 4
    with psycopg.connect(database_url) as connection:
        total = connection.execute(
            "SELECT sum(estimated_cost) FROM run_reservations "
            "WHERE user_id = %s AND status = 'reserved'",
            (user_id,),
        ).fetchone()[0]
    assert total == Decimal("1.000000")

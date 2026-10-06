from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row


@pytest.mark.database
def test_concurrent_run_costs_cannot_overspend_user_budget(database_url: str) -> None:
    user_id = uuid4()
    project_id = uuid4()
    prompt_id = uuid4()
    version_id = uuid4()
    model_config = (
        '{"provider":"mock","model":"deterministic-v1",'
        '"temperature":0,"max_output_tokens":10}'
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, display_name, password_hash)
            VALUES (%s, %s, 'Budget Racer', 'not-used')
            """,
            (user_id, f"race-{user_id}@example.com"),
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, key, owner_id)
            VALUES (%s, 'Budget Race', %s, %s)
            """,
            (project_id, f"race-{project_id.hex}", user_id),
        )
        connection.execute(
            """
            INSERT INTO prompts (id, project_id, key, name)
            VALUES (%s, %s, 'race-prompt', 'Race Prompt')
            """,
            (prompt_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            )
            VALUES (%s, %s, 1, 'Race', '[]', %s, 'Initial', %s)
            """,
            (
                version_id,
                prompt_id,
                model_config,
                user_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO budgets (user_id, monthly_limit, timezone, created_by)
            VALUES (%s, 5, 'UTC', %s)
            """,
            (user_id, user_id),
        )

    workers = 20
    barrier = Barrier(workers)

    def record(index: int) -> tuple[str, Decimal]:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            barrier.wait()
            row: dict[str, Any] | None = connection.execute(
                """
                SELECT recorded.status, recorded.cost
                FROM record_run(
                    p_user_id => %s,
                    p_project_id => %s,
                    p_prompt_id => %s,
                    p_version_id => %s,
                    p_status => 'completed',
                    p_provider => 'mock',
                    p_model => 'deterministic-v1',
                    p_input_variables => '{}'::jsonb,
                    p_output_text => 'completed',
                    p_prompt_tokens => 1,
                    p_completion_tokens => 1,
                    p_latency_ms => 1,
                    p_cost => 1,
                    p_error_code => NULL,
                    p_request_id => %s
                ) AS recorded
                """,
                (user_id, project_id, prompt_id, version_id, f"race-{index}"),
            ).fetchone()
            assert row is not None
            return row["status"], row["cost"]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(record, range(workers)))

    assert sum(status == "completed" for status, _ in results) == 5
    assert sum(status == "blocked" for status, _ in results) == 15
    assert sum(cost for _, cost in results) == Decimal("5.000000")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        totals = connection.execute(
            """
            SELECT count(*) AS run_count,
                   count(*) FILTER (WHERE status = 'completed') AS completed_count,
                   count(*) FILTER (WHERE status = 'blocked') AS blocked_count,
                   sum(cost) AS total_cost
            FROM runs
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchone()
    assert totals == {
        "run_count": 20,
        "completed_count": 5,
        "blocked_count": 15,
        "total_cost": Decimal("5.000000"),
    }

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest


def create_domain(connection: psycopg.Connection) -> tuple[UUID, UUID, UUID, UUID]:
    user_id, project_id, prompt_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO users (id, email, display_name, password_hash) VALUES (%s, %s, 'Budget', 'x')",
        (user_id, f"budget-{user_id}@example.com"),
    )
    connection.execute(
        "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Budget', %s, %s)",
        (project_id, f"budget-{project_id.hex}", user_id),
    )
    connection.execute(
        "INSERT INTO prompts (id, project_id, key, name) VALUES (%s, %s, 'p', 'Prompt')",
        (prompt_id, project_id),
    )
    connection.execute(
        """
        INSERT INTO prompt_versions (
            id, prompt_id, version_number, template_body, variables,
            model_config, commit_message, created_by
        ) VALUES (%s, %s, 1, 'Prompt', '[]',
                  '{"provider":"mock","model":"deterministic-v1",'
                  '"temperature":0,"max_output_tokens":10}', 'Initial', %s)
        """,
        (version_id, prompt_id, user_id),
    )
    return user_id, project_id, prompt_id, version_id


def record(
    connection: psycopg.Connection,
    ids: tuple[UUID, UUID, UUID, UUID],
    cost: Decimal,
    created_at: datetime | None = None,
) -> dict:
    row = connection.execute(
        """
        SELECT recorded.*
        FROM record_run(
            p_user_id => %s, p_project_id => %s, p_prompt_id => %s, p_version_id => %s,
            p_status => 'completed', p_provider => 'mock', p_model => 'deterministic-v1',
            p_input_variables => '{}'::jsonb, p_output_text => 'completed',
            p_prompt_tokens => 1, p_completion_tokens => 1, p_latency_ms => 1,
            p_cost => %s, p_error_code => NULL, p_request_id => 'budget-test',
            p_created_at => COALESCE(%s, CURRENT_TIMESTAMP)
        ) AS recorded
        """,
        (*ids, cost, created_at),
    ).fetchone()
    assert row is not None
    return row


@pytest.mark.database
def test_over_limit_run_is_recorded_as_blocked_atomically(
    db_connection: psycopg.Connection,
) -> None:
    db_connection.execute(
        "UPDATE budgets SET monthly_limit = 0 WHERE user_id = %s",
        ("11111111-1111-4111-8111-111111111111",),
    )

    run = db_connection.execute(
        """
        SELECT recorded.* FROM record_run(
            p_user_id => %s,
            p_project_id => %s,
            p_prompt_id => %s,
            p_version_id => %s,
            p_status => 'completed',
            p_provider => 'mock',
            p_model => 'deterministic-v1',
            p_input_variables => '{}'::jsonb,
            p_output_text => 'would have completed',
            p_prompt_tokens => 10,
            p_completion_tokens => 10,
            p_latency_ms => 5,
            p_cost => 0.000020,
            p_error_code => NULL,
            p_request_id => 'budget-test'
        ) AS recorded
        """,
        (
            "11111111-1111-4111-8111-111111111111",
            "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444",
            "55555555-5555-4555-8555-555555555555",
        ),
    ).fetchone()

    assert run is not None
    assert run["status"] == "blocked"
    assert run["cost"] == 0
    assert run["error_code"] == "budget_exceeded"
    assert run["output_text"] is None


@pytest.mark.database
def test_exact_limit_unlimited_and_overlapping_project_budget(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, project_id, _, _ = ids

    unlimited = record(db_connection, ids, Decimal(50))
    assert unlimited["status"] == "completed"

    db_connection.execute(
        "INSERT INTO budgets (user_id, monthly_limit) VALUES (%s, 52)",
        (user_id,),
    )
    db_connection.execute(
        "INSERT INTO budgets (project_id, monthly_limit) VALUES (%s, 51)",
        (project_id,),
    )
    exact_project_limit = record(db_connection, ids, Decimal(1))
    over_project_limit = record(db_connection, ids, Decimal(1))

    assert exact_project_limit["status"] == "completed"
    assert over_project_limit["status"] == "blocked"
    assert over_project_limit["cost"] == 0


@pytest.mark.database
def test_budget_spend_resets_at_timezone_month_boundary(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, _, _, _ = ids
    db_connection.execute(
        "INSERT INTO budgets (user_id, monthly_limit, timezone) VALUES (%s, 1, 'UTC')",
        (user_id,),
    )
    current_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if current_month.month == 12:
        next_month = current_month.replace(year=current_month.year + 1, month=1)
    else:
        next_month = current_month.replace(month=current_month.month + 1)

    first_month = record(db_connection, ids, Decimal(1), current_month)
    second_month = record(db_connection, ids, Decimal(1), next_month)

    assert first_month["status"] == "completed"
    assert second_month["status"] == "completed"


@pytest.mark.database
def test_budget_month_boundary_uses_local_wall_time_across_dst(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, _, _, _ = ids
    db_connection.execute("SELECT create_run_partition('2026-03-01'::date)")
    db_connection.execute("SELECT create_run_partition('2026-04-01'::date)")
    db_connection.execute(
        """
        INSERT INTO budgets (user_id, monthly_limit, timezone)
        VALUES (%s, 1, 'America/New_York')
        """,
        (user_id,),
    )

    april = record(
        db_connection,
        ids,
        Decimal(1),
        datetime(2026, 4, 1, 4, 30, tzinfo=UTC),
    )
    march = record(
        db_connection,
        ids,
        Decimal(1),
        datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    )

    assert april["status"] == "completed"
    assert march["status"] == "completed"


@pytest.mark.database
def test_record_run_rejects_cross_project_target_combinations(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, _, prompt_id, version_id = ids
    other_project_id = uuid4()
    db_connection.execute(
        "INSERT INTO projects (id, name, key, owner_id) VALUES (%s, 'Other', %s, %s)",
        (other_project_id, f"other-{other_project_id.hex}", user_id),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        record(
            db_connection,
            (user_id, other_project_id, prompt_id, version_id),
            Decimal(1),
        )

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest


def create_domain(
    connection: psycopg.Connection,
) -> tuple[UUID, UUID, UUID, UUID]:
    user_id, project_id, prompt_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO users (id, email, display_name, password_hash) "
        "VALUES (%s, %s, 'Reservation User', 'unused')",
        (user_id, f"reservation-{user_id}@example.com"),
    )
    connection.execute(
        "INSERT INTO projects (id, name, key, owner_id) "
        "VALUES (%s, 'Reservation Project', %s, %s)",
        (project_id, f"reservation-{project_id.hex}", user_id),
    )
    connection.execute(
        "INSERT INTO prompts (id, project_id, key, name) VALUES (%s, %s, 'p', 'Prompt')",
        (prompt_id, project_id),
    )
    connection.execute(
        '\n        INSERT INTO prompt_versions (id, prompt_id, version_number, template_body, provider, model, temperature, max_output_tokens, commit_message, created_by) VALUES (%s, %s, 1, \'Prompt\', (\'{"provider":"gemini","model":"gemini-2.5-flash",\'\n            \'"temperature":0,"max_output_tokens":100}\')::jsonb->>\'provider\', (\'{"provider":"gemini","model":"gemini-2.5-flash",\'\n            \'"temperature":0,"max_output_tokens":100}\')::jsonb->>\'model\', ((\'{"provider":"gemini","model":"gemini-2.5-flash",\'\n            \'"temperature":0,"max_output_tokens":100}\')::jsonb->>\'temperature\')::numeric, ((\'{"provider":"gemini","model":"gemini-2.5-flash",\'\n            \'"temperature":0,"max_output_tokens":100}\')::jsonb->>\'max_output_tokens\')::integer, \'Initial\', %s)\n        ',
        (version_id, prompt_id, user_id),
    )
    return user_id, project_id, prompt_id, version_id


def reserve(
    connection: psycopg.Connection,
    ids: tuple[UUID, UUID, UUID, UUID],
    *,
    key: str,
    fingerprint: str,
    estimated_cost: Decimal,
    maximum_concurrent: int = 2,
) -> dict:
    row = connection.execute(
        """
        SELECT reserved.* FROM reserve_run_execution(
            p_user_id => %s,
            p_project_id => %s,
            p_prompt_id => %s,
            p_version_id => %s,
            p_idempotency_key => %s,
            p_request_fingerprint => %s,
            p_claim_token => %s,
            p_estimated_cost => %s,
            p_maximum_concurrent => %s
        ) AS reserved
        """,
        (*ids, key, fingerprint, uuid4(), estimated_cost, maximum_concurrent),
    ).fetchone()
    assert row is not None
    return row


@pytest.mark.database
def test_budget_is_reserved_before_execution_and_duplicate_key_is_reused(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, project_id, _, _ = ids
    db_connection.execute(
        "INSERT INTO budgets (user_id, monthly_limit) VALUES (%s, 1)",
        (user_id,),
    )
    db_connection.execute(
        "INSERT INTO budgets (project_id, monthly_limit) VALUES (%s, 1)",
        (project_id,),
    )

    first = reserve(
        db_connection,
        ids,
        key="reservation-key-0001",
        fingerprint="a" * 64,
        estimated_cost=Decimal("0.75"),
    )
    duplicate = reserve(
        db_connection,
        ids,
        key="reservation-key-0001",
        fingerprint="a" * 64,
        estimated_cost=Decimal("0.75"),
    )
    over_budget = reserve(
        db_connection,
        ids,
        key="reservation-key-0002",
        fingerprint="b" * 64,
        estimated_cost=Decimal("0.50"),
    )

    assert first["status"] == "reserved"
    assert duplicate["id"] == first["id"]
    assert over_budget["status"] == "blocked"
    assert over_budget["error_code"] == "budget_exceeded"
    assert (
        db_connection.execute(
            "SELECT count(*) FROM reservation_context WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
        == 2
    )


@pytest.mark.database
def test_idempotency_key_rejects_a_different_request_and_limits_concurrency(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)

    first = reserve(
        db_connection,
        ids,
        key="reservation-key-0003",
        fingerprint="c" * 64,
        estimated_cost=Decimal("0.10"),
        maximum_concurrent=1,
    )
    limited = reserve(
        db_connection,
        ids,
        key="reservation-key-0004",
        fingerprint="d" * 64,
        estimated_cost=Decimal("0.10"),
        maximum_concurrent=1,
    )

    assert first["status"] == "reserved"
    assert limited["status"] == "blocked"
    assert limited["error_code"] == "concurrency_limit"
    with pytest.raises(psycopg.errors.RaiseException, match="idempotency_conflict"):
        reserve(
            db_connection,
            ids,
            key="reservation-key-0003",
            fingerprint="e" * 64,
            estimated_cost=Decimal("0.10"),
            maximum_concurrent=1,
        )


@pytest.mark.database
def test_completed_reservation_reconciles_estimate_to_actual_run_cost(
    db_connection: psycopg.Connection,
) -> None:
    ids = create_domain(db_connection)
    user_id, _, _, _ = ids
    db_connection.execute(
        "INSERT INTO budgets (user_id, monthly_limit) VALUES (%s, 1)",
        (user_id,),
    )
    reservation = reserve(
        db_connection,
        ids,
        key="reservation-key-0005",
        fingerprint="f" * 64,
        estimated_cost=Decimal("0.75"),
    )
    run = db_connection.execute(
        """
        SELECT recorded.* FROM record_run(
            p_user_id => %s, p_project_id => %s, p_prompt_id => %s, p_version_id => %s,
            p_status => 'completed', p_provider => 'gemini', p_model => 'gemini-2.5-flash',
            p_input_variables => '{}'::jsonb, p_output_text => 'done',
            p_prompt_tokens => 1, p_completion_tokens => 1, p_latency_ms => 1,
            p_cost => 0.25, p_error_code => NULL, p_request_id => 'reservation-finalize'
        ) AS recorded
        """,
        ids,
    ).fetchone()
    assert run is not None

    reconciled = db_connection.execute(
        """
        SELECT finalized.* FROM finalize_run_execution(
            p_reservation_id => %s,
            p_status => 'completed',
            p_actual_cost => 0.25,
            p_run_id => %s,
            p_run_created_at => %s,
            p_error_code => NULL
        ) AS finalized
        """,
        (reservation["id"], run["id"], run["created_at"]),
    ).fetchone()
    assert reconciled is not None
    assert reconciled["status"] == "completed"
    assert reconciled["actual_cost"] == Decimal("0.250000")

    next_reservation = reserve(
        db_connection,
        ids,
        key="reservation-key-0006",
        fingerprint="0" * 64,
        estimated_cost=Decimal("0.75"),
    )
    assert next_reservation["status"] == "reserved"

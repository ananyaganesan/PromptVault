import psycopg
import pytest


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
        SELECT (record_run(
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
        )).*
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

import psycopg
import pytest


@pytest.mark.database
def test_current_runs_are_routed_to_a_month_partition(
    db_connection: psycopg.Connection,
) -> None:
    run = db_connection.execute(
        """
        SELECT (record_run(
            p_user_id => %s,
            p_project_id => %s,
            p_prompt_id => %s,
            p_version_id => %s,
            p_status => 'completed',
            p_provider => 'gemini',
            p_model => 'gemini-3.5-flash-lite',
            p_input_variables => '{}'::jsonb,
            p_output_text => 'ok',
            p_prompt_tokens => 1,
            p_completion_tokens => 1,
            p_latency_ms => 1,
            p_cost => 0,
            p_error_code => NULL,
            p_request_id => 'partition-test'
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

    stored = db_connection.execute(
        "SELECT tableoid::regclass::text AS partition FROM runs WHERE id = %s",
        (run["id"],),
    ).fetchone()

    assert stored is not None
    assert stored["partition"].startswith("runs_")

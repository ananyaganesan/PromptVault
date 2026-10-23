import psycopg
import pytest


@pytest.mark.database
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_prompt_versions_cannot_be_changed(
    db_connection: psycopg.Connection,
    operation: str,
) -> None:
    statement = (
        "UPDATE prompt_versions SET commit_message = 'changed' "
        "WHERE id = '55555555-5555-4555-8555-555555555555'"
        if operation == "UPDATE"
        else "DELETE FROM prompt_versions WHERE id = '55555555-5555-4555-8555-555555555555'"
    )

    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        db_connection.transaction(),
    ):
        db_connection.execute(statement)


@pytest.mark.database
def test_runs_are_append_only(db_connection: psycopg.Connection) -> None:
    run = db_connection.execute(
        """
        SELECT (record_run(
            p_user_id => %s,
            p_project_id => %s,
            p_prompt_id => %s,
            p_version_id => %s,
            p_status => 'failed',
            p_provider => 'gemini',
            p_model => 'gemini-3.5-flash-lite',
            p_input_variables => '{}'::jsonb,
            p_output_text => NULL,
            p_prompt_tokens => 0,
            p_completion_tokens => 0,
            p_latency_ms => 1,
            p_cost => 0,
            p_error_code => 'provider_error',
            p_request_id => 'immutability-test'
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

    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        db_connection.transaction(),
    ):
        db_connection.execute(
            "UPDATE runs SET error_code = 'changed' WHERE id = %s",
            (run["id"],),
        )

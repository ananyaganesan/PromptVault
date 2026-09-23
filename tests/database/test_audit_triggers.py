import psycopg
import pytest


@pytest.mark.database
def test_audit_trigger_records_actor_request_and_redacted_change(
    db_connection: psycopg.Connection,
) -> None:
    actor_id = "22222222-2222-4222-8222-222222222222"
    request_id = "audit-trigger-test"
    db_connection.execute("SELECT set_config('app.user_id', %s, true)", (actor_id,))
    db_connection.execute("SELECT set_config('app.request_id', %s, true)", (request_id,))
    db_connection.execute(
        "UPDATE projects SET description = 'Audited description' WHERE id = %s",
        ("33333333-3333-4333-8333-333333333333",),
    )

    event = db_connection.execute(
        """
        SELECT actor_user_id, action, entity_type, entity_id, before_data, after_data
        FROM audit_events
        WHERE request_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()

    assert event is not None
    assert str(event["actor_user_id"]) == actor_id
    assert event["action"] == "update"
    assert event["entity_type"] == "projects"
    assert event["before_data"]["description"] != event["after_data"]["description"]

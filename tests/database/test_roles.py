import psycopg
import pytest


@pytest.mark.database
@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("users", "password_hash"),
        ("provider_keys", "encrypted_secret"),
        ("api_tokens", "token_hash"),
    ],
)
def test_readonly_role_cannot_select_secret_columns(
    db_connection: psycopg.Connection,
    table: str,
    column: str,
) -> None:
    row = db_connection.execute(
        "SELECT has_column_privilege('promptvault_readonly', %s, %s, 'SELECT') AS allowed",
        (table, column),
    ).fetchone()

    assert row is not None
    assert row["allowed"] is False


@pytest.mark.database
def test_readonly_role_can_select_safe_user_metadata(
    db_connection: psycopg.Connection,
) -> None:
    row = db_connection.execute(
        "SELECT has_column_privilege('promptvault_readonly', 'users', 'email', 'SELECT') AS allowed"
    ).fetchone()

    assert row is not None
    assert row["allowed"] is True


@pytest.mark.database
def test_application_role_can_only_insert_runs_through_budget_function(
    db_connection: psycopg.Connection,
) -> None:
    privileges = db_connection.execute(
        """
        SELECT has_table_privilege('promptvault_app', 'runs', 'INSERT') AS direct_insert,
               (
                   SELECT bool_or(has_table_privilege(
                       'promptvault_app', inhrelid::regclass, 'INSERT'
                   ))
                   FROM pg_inherits
                   WHERE inhparent = 'runs'::regclass
               ) AS partition_insert,
               has_function_privilege(
                   'promptvault_app',
                   'record_run(uuid,uuid,uuid,uuid,run_status,text,text,jsonb,text,'
                   'integer,integer,integer,numeric,text,text,timestamptz)',
                   'EXECUTE'
               ) AS function_execute
        """
    ).fetchone()

    assert privileges is not None
    assert privileges["direct_insert"] is False
    assert privileges["partition_insert"] is False
    assert privileges["function_execute"] is True


@pytest.mark.database
def test_application_role_has_only_required_governance_write_boundaries(
    db_connection: psycopg.Connection,
) -> None:
    privileges = db_connection.execute(
        """
        SELECT has_function_privilege(
                   'promptvault_app',
                   'admin_update_user(uuid,uuid,user_role,boolean,boolean,boolean)',
                   'EXECUTE'
               ) AS user_transition,
               has_table_privilege(
                   'promptvault_app', 'budgets', 'DELETE'
               ) AS budget_delete,
               has_table_privilege(
                   'promptvault_app', 'users', 'UPDATE'
               ) AS direct_user_update
        """
    ).fetchone()

    assert privileges is not None
    assert privileges["user_transition"] is True
    assert privileges["budget_delete"] is True
    assert privileges["direct_user_update"] is False


@pytest.mark.database
def test_application_role_executes_audited_maintenance_wrappers(
    db_connection: psycopg.Connection,
) -> None:
    privileges = db_connection.execute(
        """
        SELECT has_function_privilege(
                   'promptvault_app',
                   'admin_refresh_reporting_views(uuid,text)',
                   'EXECUTE'
               ) AS refresh_views,
               has_function_privilege(
                   'promptvault_app',
                   'admin_create_next_run_partition(uuid,text)',
                   'EXECUTE'
               ) AS create_partition
        """
    ).fetchone()

    assert privileges is not None
    assert privileges["refresh_views"] is True
    assert privileges["create_partition"] is True

    db_connection.execute("SET LOCAL ROLE promptvault_app")
    refreshed_at = db_connection.execute(
        "SELECT admin_refresh_reporting_views(%s, %s) AS completed_at",
        ("22222222-2222-4222-8222-222222222222", "role-refresh-test"),
    ).fetchone()["completed_at"]
    partition = db_connection.execute(
        "SELECT * FROM admin_create_next_run_partition(%s, %s)",
        ("22222222-2222-4222-8222-222222222222", "role-partition-test"),
    ).fetchone()

    assert refreshed_at is not None
    assert partition["partition_name"].startswith("runs_")

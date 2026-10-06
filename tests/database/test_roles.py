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
def test_application_role_uses_function_boundaries_for_versions_and_deployments(
    db_connection: psycopg.Connection,
) -> None:
    privileges = db_connection.execute(
        """
        SELECT has_table_privilege(
                   'promptvault_app', 'prompt_versions', 'INSERT'
               ) AS direct_version_insert,
               has_table_privilege(
                   'promptvault_app', 'deployments', 'INSERT'
               ) AS direct_deployment_insert,
               has_table_privilege(
                   'promptvault_app', 'deployments', 'UPDATE'
               ) AS direct_deployment_update,
               has_function_privilege(
                   'promptvault_app',
                   'create_prompt_version(uuid,uuid,text,jsonb,jsonb,text,uuid)',
                   'EXECUTE'
               ) AS version_function,
               has_function_privilege(
                   'promptvault_app',
                   'request_deployment(uuid,deployment_environment,uuid,text)',
                   'EXECUTE'
               ) AS deployment_function
        """
    ).fetchone()

    assert privileges is not None
    assert privileges["direct_version_insert"] is False
    assert privileges["direct_deployment_insert"] is False
    assert privileges["direct_deployment_update"] is False
    assert privileges["version_function"] is True
    assert privileges["deployment_function"] is True

    db_connection.execute("SET LOCAL ROLE promptvault_app")
    version = db_connection.execute(
        """
        SELECT (create_prompt_version(
            %s, %s, 'Role boundary {{name}}', '["name"]',
            '{"provider":"mock","model":"deterministic-v1",'
            '"temperature":0,"max_output_tokens":50}',
            'Role boundary version', %s
        )).*
        """,
        (
            "44444444-4444-4444-8444-444444444444",
            "55555555-5555-4555-8555-555555555555",
            "11111111-1111-4111-8111-111111111111",
        ),
    ).fetchone()
    assert version is not None
    deployment = db_connection.execute(
        "SELECT (request_deployment(%s, 'staging', %s, NULL)).status AS status",
        (
            version["id"],
            "11111111-1111-4111-8111-111111111111",
        ),
    ).fetchone()
    assert deployment is not None
    assert deployment["status"] == "active"


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

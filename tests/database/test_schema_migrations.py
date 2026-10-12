from pathlib import Path

import pytest
from pglast import parse_sql

from api.app.db.migrations import discover_migrations

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIRECTORY = REPOSITORY_ROOT / "db" / "migrations"


def migration_sql(version: int) -> str:
    path = next(MIGRATIONS_DIRECTORY.glob(f"{version:03d}_*.sql"))
    return path.read_text(encoding="utf-8").lower()


def test_complete_migration_chain_is_discoverable() -> None:
    migrations = discover_migrations(MIGRATIONS_DIRECTORY)

    assert [migration.version for migration in migrations] == list(range(1, 24))


@pytest.mark.parametrize("path", sorted(MIGRATIONS_DIRECTORY.glob("*.sql")), ids=lambda p: p.name)
def test_migration_has_valid_postgresql_syntax(path: Path) -> None:
    parse_sql(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "table",
    [
        "users",
        "projects",
        "project_members",
        "prompts",
        "prompt_versions",
        "model_pricing",
        "budgets",
        "provider_keys",
        "api_tokens",
        "deployments",
        "runs",
        "audit_events",
    ],
)
def test_domain_tables_are_declared(table: str) -> None:
    assert f"create table {table}" in migration_sql(2)


def test_run_ledger_is_monthly_partitioned() -> None:
    assert "partition by range (created_at)" in migration_sql(2)
    partitions = migration_sql(4)
    assert "create_run_partition" in partitions
    assert "date_trunc('month'" in partitions


def test_constraints_encode_critical_domain_invariants() -> None:
    constraints = migration_sql(3)

    assert "num_nonnulls(user_id, project_id) = 1" in constraints
    assert "unique (prompt_id, version_number)" in constraints
    assert "where status = 'active'" in constraints
    assert "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$" in constraints
    assert "exclude using gist" in constraints


def test_history_tables_have_immutability_guards() -> None:
    triggers = migration_sql(5)

    assert "prompt_versions_are_immutable" in triggers
    assert "runs_are_append_only" in triggers
    assert "audit_events_are_append_only" in triggers


def test_concurrency_sensitive_functions_take_row_locks() -> None:
    functions = migration_sql(6)

    assert "create_prompt_version" in functions
    assert "review_production_deployment" in functions
    assert "rollback_deployment" in functions
    assert "record_run" in functions
    assert functions.count("for update") >= 4


def test_reporting_views_and_refreshable_aggregates_exist() -> None:
    assert "create view prompt_version_lineage" in migration_sql(7)
    aggregates = migration_sql(8)
    assert "create materialized view organization_monthly_metrics" in aggregates
    assert "create materialized view user_monthly_metrics" in aggregates


def test_database_roles_follow_least_privilege_shape() -> None:
    grants = migration_sql(9)

    assert "promptvault_app" in grants
    assert "promptvault_readonly" in grants
    assert "revoke all on" in grants
    assert "grant execute on function" in grants


def test_password_reset_uses_a_restricted_database_function() -> None:
    boundary = migration_sql(16)

    assert "security definer" in boundary
    assert "consume_password_reset_token" in boundary
    assert "grant execute on function" in boundary


def test_admin_self_transition_preserves_last_admin_guard() -> None:
    boundary = migration_sql(17)

    assert "admin_update_user" in boundary
    assert "last_admin" in boundary
    assert "for update" in boundary


def test_password_history_is_recorded_by_database_trigger() -> None:
    history = migration_sql(18)

    assert "create table password_history" in history
    assert "record_password_history" in history
    assert "after insert or update of password_hash" in history


def test_execution_reservations_protect_paid_calls_before_provider_use() -> None:
    reservations = migration_sql(19)

    assert "create table run_reservations" in reservations
    assert "reserve_run_execution" in reservations
    assert "finalize_run_execution" in reservations
    assert "idempotency_key" in reservations
    assert "status in ('reserved', 'completed', 'failed', 'uncertain', 'blocked')" in reservations


def test_auth_sessions_support_revocation_and_password_reset_invalidation() -> None:
    sessions = migration_sql(20)

    assert "create table auth_sessions" in sessions
    assert "revoked_at" in sessions
    assert "password_reset" in sessions
    assert "consume_password_reset_token" in sessions


def test_system_maintenance_is_an_actual_stored_procedure() -> None:
    maintenance = migration_sql(21)

    assert "create or replace procedure perform_system_maintenance" in maintenance
    assert "update run_reservations" in maintenance
    assert "delete from auth_sessions" in maintenance
    assert "refresh materialized view" in maintenance


def test_account_closure_is_atomic_and_revokes_credentials() -> None:
    lifecycle = migration_sql(22)

    assert "create or replace function close_user_account" in lifecycle
    assert "update auth_sessions" in lifecycle
    assert "update api_tokens" in lifecycle
    assert "pseudonymized" in lifecycle


def test_seed_files_define_deterministic_demo_identities() -> None:
    seeds_directory = REPOSITORY_ROOT / "db" / "seeds"
    seed_names = [path.name for path in sorted(seeds_directory.glob("*.sql"))]
    assert seed_names == [
        "001_development.sql",
        "002_demo.sql",
        "003_auth_test_users.sql",
        "004_recent_runs.sql",
    ]

    development = (seeds_directory / "001_development.sql").read_text(
        encoding="utf-8"
    ).lower()
    demo = (seeds_directory / "002_demo.sql").read_text(encoding="utf-8").lower()

    assert "user@promptvault.dev" in development
    assert "admin@promptvault.dev" in development
    assert "on conflict" in development
    assert "checkout-assistant" in demo
    assert "on conflict" in demo

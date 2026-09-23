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

import psycopg
import pytest


@pytest.mark.database
def test_email_uniqueness_is_case_insensitive(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation), db_connection.transaction():
        db_connection.execute(
            """
            INSERT INTO users (email, display_name, password_hash)
            VALUES ('USER@PROMPTVAULT.DEV', 'Duplicate', 'not-a-real-hash')
            """
        )


@pytest.mark.database
def test_project_keys_are_globally_unique_and_valid(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), db_connection.transaction():
        db_connection.execute(
            """
            INSERT INTO projects (name, key, owner_id)
            VALUES ('Invalid project', 'Not Valid', %s)
            """,
            ("11111111-1111-4111-8111-111111111111",),
        )

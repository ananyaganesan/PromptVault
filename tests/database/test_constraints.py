from uuid import uuid4

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


@pytest.mark.database
def test_runs_reject_cross_project_prompt_relationships(
    db_connection: psycopg.Connection,
) -> None:
    project_id = uuid4()
    db_connection.execute(
        """INSERT INTO projects (id, name, key, owner_id)
           VALUES (%s, 'Other project', %s, %s)""",
        (
            project_id,
            f"other-{project_id.hex}",
            "11111111-1111-4111-8111-111111111111",
        ),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO runs (
                   user_id, project_id, prompt_id, version_id, status, provider, model,
                   output_text, prompt_tokens, completion_tokens, latency_ms, cost
               ) VALUES (%s, %s, %s, %s, 'completed', 'mock', 'deterministic-v1',
                         'ok', 1, 1, 1, 0)""",
            (
                "11111111-1111-4111-8111-111111111111",
                project_id,
                "44444444-4444-4444-8444-444444444444",
                "55555555-5555-4555-8555-555555555555",
            ),
        )


@pytest.mark.database
def test_token_revocation_metadata_must_be_complete(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO api_tokens (
                   project_id, name, token_prefix, token_hash, created_by, revoked_at
               ) VALUES (%s, 'Invalid revoked token', 'pv_live_invalid', %s, %s, now())""",
            (
                "33333333-3333-4333-8333-333333333333",
                "a" * 64,
                "11111111-1111-4111-8111-111111111111",
            ),
        )


@pytest.mark.database
def test_provider_key_deactivation_cannot_precede_creation(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO provider_keys (
                   provider, alias, encrypted_secret, created_by, created_at, deactivated_at
               ) VALUES ('mock', %s, %s, %s, now(), now() - interval '1 minute')""",
            (
                f"invalid-{uuid4().hex}",
                b"ciphertext",
                "22222222-2222-4222-8222-222222222222",
            ),
        )


@pytest.mark.database
def test_pending_deployment_rejects_review_metadata(
    db_connection: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO deployments (
                   prompt_id, version_id, environment, status, requested_by,
                   reviewed_by, reviewed_at
               ) VALUES (%s, %s, 'prod', 'pending', %s, %s, now())""",
            (
                "44444444-4444-4444-8444-444444444444",
                "55555555-5555-4555-8555-555555555555",
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
            ),
        )


@pytest.mark.database
def test_rollback_reference_must_match_prompt_and_environment(
    db_connection: psycopg.Connection,
) -> None:
    original_id = uuid4()
    db_connection.execute(
        """INSERT INTO deployments (
               id, prompt_id, version_id, environment, status, requested_by, activated_at
           ) VALUES (%s, %s, %s, 'dev', 'active', %s, now())""",
        (
            original_id,
            "44444444-4444-4444-8444-444444444444",
            "55555555-5555-4555-8555-555555555555",
            "11111111-1111-4111-8111-111111111111",
        ),
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO deployments (
                   prompt_id, version_id, environment, status, rollback_reason,
                   rollback_of_id, requested_by, reviewed_by, reviewed_at, activated_at
               ) VALUES (%s, %s, 'staging', 'active', 'Invalid cross-environment rollback',
                         %s, %s, %s, now(), now())""",
            (
                "44444444-4444-4444-8444-444444444444",
                "55555555-5555-4555-8555-555555555555",
                original_id,
                "22222222-2222-4222-8222-222222222222",
                "22222222-2222-4222-8222-222222222222",
            ),
        )

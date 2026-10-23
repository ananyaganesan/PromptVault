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
        "INSERT INTO projects (id,name,key,owner_id) VALUES (%s,'Other',%s,'11111111-1111-4111-8111-111111111111')",
        (project_id, "other-" + project_id.hex),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db_connection.transaction():
        db_connection.execute(
            """SELECT record_run(
          '11111111-1111-4111-8111-111111111111',%s,
          '44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555',
          'completed','gemini','gemini-3.5-flash-lite','{}','ok',1,1,1,0,NULL,'invalid-context')""",
            (project_id,),
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
               ) VALUES ('gemini', %s, %s, %s, now(), now() - interval '1 minute')""",
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
        db_connection.execute("""INSERT INTO deployments(version_id,environment,status,requested_by,reviewed_by,reviewed_at)
          VALUES ('55555555-5555-4555-8555-555555555555','prod','pending',
          '11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222',now())""")


@pytest.mark.database
def test_rollback_reference_must_match_prompt_and_environment(
    db_connection: psycopg.Connection,
) -> None:
    original_id, rollback_id = uuid4(), uuid4()
    second = db_connection.execute("""SELECT (create_prompt_version(
     '44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555',
     'Second','[]','{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":10}',
     'Scope fixture','11111111-1111-4111-8111-111111111111')).id""").fetchone()["id"]
    db_connection.execute(
        """INSERT INTO deployments(id,version_id,environment,status,requested_by,activated_at)
     VALUES(%s,%s,'dev','active','11111111-1111-4111-8111-111111111111',now())""",
        (original_id, second),
    )
    with pytest.raises(psycopg.errors.CheckViolation), db_connection.transaction():
        db_connection.execute(
            """INSERT INTO deployments(id,version_id,environment,status,requested_by,activated_at)
          VALUES(%s,'55555555-5555-4555-8555-555555555555','staging','active',
          '11111111-1111-4111-8111-111111111111',now())""",
            (rollback_id,),
        )
        db_connection.execute(
            "INSERT INTO deployment_rollbacks(deployment_id,rollback_of_id,reason) VALUES(%s,%s,'Invalid cross-environment rollback')",
            (rollback_id, original_id),
        )

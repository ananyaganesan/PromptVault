from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_materialized_views_can_be_refreshed_after_migration(database_url: str) -> None:
    refresh_sql = (
        REPOSITORY_ROOT / "db" / "maintenance" / "refresh-views.sql"
    ).read_text(encoding="utf-8")

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(refresh_sql)
        rows = connection.execute(
            """
            SELECT matviewname, ispopulated
            FROM pg_matviews
            WHERE schemaname = 'public'
              AND matviewname IN (
                  'organization_monthly_metrics',
                  'user_monthly_metrics'
              )
            ORDER BY matviewname
            """
        ).fetchall()

    assert rows == [
        ("organization_monthly_metrics", True),
        ("user_monthly_metrics", True),
    ]


@pytest.mark.database
def test_system_maintenance_recovers_stale_reservations_and_cleans_tokens(
    db_connection,
) -> None:
    reservation_id = uuid4()
    session_id = uuid4()
    token_hash = uuid4().hex + uuid4().hex
    db_connection.execute(
        """
        INSERT INTO run_reservations (
            id, idempotency_key, request_fingerprint, claim_token, user_id,
            version_id, estimated_cost, status, created_at
        ) VALUES (
            %s, %s, %s, %s, '11111111-1111-4111-8111-111111111111',
            '55555555-5555-4555-8555-555555555555', 0.25, 'reserved',
            CURRENT_TIMESTAMP - INTERVAL '20 minutes'
        )
        """,
        (reservation_id, f"maintenance-{uuid4()}", "f" * 64, uuid4()),
    )
    db_connection.execute(
        """
        INSERT INTO auth_sessions (id, user_id, issued_at, expires_at)
        VALUES (%s, '11111111-1111-4111-8111-111111111111',
                CURRENT_TIMESTAMP - INTERVAL '62 days',
                CURRENT_TIMESTAMP - INTERVAL '61 days')
        """,
        (session_id,),
    )
    db_connection.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
        VALUES ('11111111-1111-4111-8111-111111111111', %s,
                CURRENT_TIMESTAMP - INTERVAL '61 days')
        """,
        (token_hash,),
    )

    db_connection.execute(
        "CALL perform_system_maintenance('10 minutes', '30 days', '30 days')"
    )

    assert db_connection.execute(
        "SELECT status, error_code FROM reservation_context WHERE id = %s",
        (reservation_id,),
    ).fetchone() == {"status": "uncertain", "error_code": "execution_interrupted"}
    assert (
        db_connection.execute(
            "SELECT count(*) AS count FROM auth_sessions WHERE id = %s", (session_id,)
        ).fetchone()["count"]
        == 0
    )
    assert (
        db_connection.execute(
            "SELECT count(*) AS count FROM password_reset_tokens WHERE token_hash = %s",
            (token_hash,),
        ).fetchone()["count"]
        == 0
    )

from pathlib import Path

import psycopg
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_materialized_views_can_be_refreshed_after_migration(database_url: str) -> None:
    refresh_sql = (REPOSITORY_ROOT / "db" / "maintenance" / "refresh-views.sql").read_text(
        encoding="utf-8"
    )

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

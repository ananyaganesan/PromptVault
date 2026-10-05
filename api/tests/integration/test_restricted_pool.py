import pytest
from api.app.config import Settings
from api.app.db.pool import create_pool


@pytest.mark.database
@pytest.mark.asyncio
async def test_pool_assumes_restricted_application_role(
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "database_role": "promptvault_app",
            "db_pool_min_size": 1,
            "db_pool_max_size": 1,
        }
    )
    pool = create_pool(settings)
    await pool.open(wait=True)
    try:
        async with pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT current_user, session_user, "
                "has_table_privilege(current_user, 'users', 'UPDATE') AS user_update"
            )
            row = await cursor.fetchone()
        assert row is not None
        assert row["current_user"] == "promptvault_app"
        assert row["session_user"] != "promptvault_app"
        assert row["user_update"] is False
    finally:
        await pool.close()

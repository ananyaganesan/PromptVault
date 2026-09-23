from uuid import UUID

import psycopg
import pytest
from api.app.repositories.runs import RunRepository
from psycopg.rows import dict_row

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("55555555-5555-4555-8555-555555555555")


@pytest.mark.database
@pytest.mark.asyncio
async def test_run_recording_access_lock_blocks_concurrent_user_deactivation(
    seeded_database_url: str,
) -> None:
    async with await psycopg.AsyncConnection.connect(
        seeded_database_url,
        row_factory=dict_row,
    ) as recording_connection, recording_connection.transaction():
        allowed = await RunRepository(recording_connection).lock_execution_access(
            VERSION_ID,
            USER_ID,
        )
        assert allowed is True

        admin_connection = psycopg.connect(seeded_database_url)
        try:
            admin_connection.execute("SET lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                admin_connection.execute(
                    "UPDATE users SET is_active = FALSE WHERE id = %s",
                    (USER_ID,),
                )
        finally:
            admin_connection.rollback()
            admin_connection.close()

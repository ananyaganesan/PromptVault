from uuid import UUID

import psycopg
import pytest
from api.app.repositories.deployments import DeploymentRepository
from tests.orm_support import orm_connection

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
VERSION_ID = UUID("55555555-5555-4555-8555-555555555555")


@pytest.mark.database
@pytest.mark.asyncio
async def test_deployment_access_lock_blocks_concurrent_membership_removal(
    seeded_database_url: str,
) -> None:
    async with (
        orm_connection(seeded_database_url) as deployment_connection,
        deployment_connection.transaction(),
    ):
        allowed = await DeploymentRepository(deployment_connection).lock_version_access(
            VERSION_ID, USER_ID, "user"
        )
        assert allowed is True

        owner_connection = psycopg.connect(seeded_database_url)
        try:
            owner_connection.execute("SET lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                owner_connection.execute(
                    "DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
                    (PROJECT_ID, USER_ID),
                )
        finally:
            owner_connection.rollback()
            owner_connection.close()

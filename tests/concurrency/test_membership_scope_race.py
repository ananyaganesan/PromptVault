from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from api.app.repositories.projects import ProjectRepository
from api.app.repositories.prompts import PromptRepository
from tests.orm_support import orm_connection

OWNER_ID = "11111111-1111-4111-8111-111111111111"


def create_member_prompt(database_url: str) -> tuple[UUID, UUID, UUID]:
    member_id = uuid4()
    project_id = uuid4()
    prompt_id = uuid4()
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, display_name, password_hash)
            VALUES (%s, %s, 'Race Member', 'not-used')
            """,
            (member_id, f"race-{uuid4()}@example.com"),
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, key, owner_id)
            VALUES (%s, 'Race Project', %s, %s)
            """,
            (project_id, f"race-{uuid4().hex}", OWNER_ID),
        )
        connection.execute(
            """
            INSERT INTO project_members (project_id, user_id, added_by)
            VALUES (%s, %s, %s)
            """,
            (project_id, member_id, OWNER_ID),
        )
        connection.execute(
            """
            INSERT INTO prompts (id, project_id, key, name)
            VALUES (%s, %s, 'race-prompt', 'Race Prompt')
            """,
            (prompt_id, project_id),
        )
    return member_id, project_id, prompt_id


@pytest.mark.database
@pytest.mark.parametrize("scope", ["project", "prompt"])
async def test_membership_removal_waits_for_inflight_scoped_work(
    database_url: str,
    scope: str,
) -> None:
    member_id, project_id, prompt_id = create_member_prompt(database_url)
    access_context = orm_connection(database_url)
    access_connection = await access_context.__aenter__()
    remover_connection = await psycopg.AsyncConnection.connect(
        database_url, row_factory=dict_row
    )
    try:
        async with access_connection.transaction():
            if scope == "project":
                allowed = await ProjectRepository(access_connection).lock_member_access(
                    project_id, member_id, "user"
                )
            else:
                allowed = await PromptRepository(access_connection).lock_member_access(
                    prompt_id, member_id, "user"
                )
            assert allowed is True

            with pytest.raises(psycopg.errors.LockNotAvailable):
                async with remover_connection.transaction():
                    await remover_connection.execute("SET LOCAL lock_timeout = '100ms'")
                    await remover_connection.execute(
                        "DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
                        (project_id, member_id),
                    )

        async with remover_connection.transaction():
            removed = await remover_connection.execute(
                "DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
                (project_id, member_id),
            )
            assert removed.rowcount == 1
    finally:
        await access_context.__aexit__(None, None, None)
        await remover_connection.close()

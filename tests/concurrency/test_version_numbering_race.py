from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

USER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.database
def test_concurrent_version_saves_allocate_unique_consecutive_numbers(
    database_url: str,
) -> None:
    project_id = uuid4()
    prompt_id = uuid4()
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        connection.execute(
            """
            INSERT INTO projects (id, name, key, owner_id)
            VALUES (%s, 'Concurrency Project', %s, %s)
            """,
            (project_id, f"concurrency-{uuid4().hex}", USER_ID),
        )
        connection.execute(
            """
            INSERT INTO prompts (id, project_id, key, name)
            VALUES (%s, %s, 'race-prompt', 'Race Prompt')
            """,
            (prompt_id, project_id),
        )
        initial = connection.execute(
            """
            SELECT * FROM create_prompt_version(
                %s, NULL, 'Initial {{value}}', '["value"]'::jsonb,
                '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":100}'::jsonb,
                'Initial', %s
            )
            """,
            (prompt_id, USER_ID),
        ).fetchone()
    assert initial is not None

    def save_version(index: int) -> int:
        with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT * FROM create_prompt_version(
                    %s, %s, %s, '["value"]'::jsonb,
                    '{"provider":"gemini","model":"gemini-3.5-flash-lite","temperature":0,"max_output_tokens":100}'::jsonb,
                    %s, %s
                )
                """,
                (
                    prompt_id,
                    initial["id"],
                    f"Concurrent {{{{value}}}} save {index}",
                    f"Concurrent save {index}",
                    USER_ID,
                ),
            ).fetchone()
        assert row is not None
        return int(row["version_number"])

    with ThreadPoolExecutor(max_workers=20) as executor:
        numbers = list(executor.map(save_version, range(20)))

    assert sorted(numbers) == list(range(2, 22))
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        count = connection.execute(
            "SELECT count(*) AS total FROM prompt_versions WHERE prompt_id = %s",
            (prompt_id,),
        ).fetchone()
    assert count is not None
    assert count["total"] == 21

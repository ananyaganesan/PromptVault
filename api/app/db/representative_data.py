"""Deterministic representative data for repeatable query-plan checks."""

from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID, uuid5

import psycopg

_NAMESPACE = UUID("72bed0fd-713e-4bc4-aea4-0697ae8bab3d")
PERFORMANCE_USER_ID = uuid5(_NAMESPACE, "user")
PERFORMANCE_PROJECT_ID = uuid5(_NAMESPACE, "project")
PERFORMANCE_PROMPT_ID = uuid5(_NAMESPACE, "prompt")
PERFORMANCE_VERSION_ID = uuid5(_NAMESPACE, "version")
_DISTRACTOR_USER_ID = uuid5(_NAMESPACE, "distractor-user")
_DISTRACTOR_PROJECT_ID = uuid5(_NAMESPACE, "distractor-project")
_DISTRACTOR_PROMPT_ID = uuid5(_NAMESPACE, "distractor-prompt")
_DISTRACTOR_VERSION_ID = uuid5(_NAMESPACE, "distractor-version")


class RepresentativeDataSummary(TypedDict):
    project_id: UUID
    user_id: UUID
    prompt_id: UUID
    version_id: UUID
    run_count: int
    partition: str


def seed_representative_dataset(
    database_url: str, *, run_count: int = 2_000
) -> RepresentativeDataSummary:
    """Create one realistic project ledger; repeated calls do not duplicate rows."""

    if run_count < 1:
        raise ValueError("run_count must be positive")
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    with psycopg.connect(database_url) as connection:
        partition_row = connection.execute(
            "SELECT create_run_partition(%s::date)", (month_start.date(),)
        ).fetchone()
        if partition_row is None:
            raise RuntimeError("partition creation returned no row")
        partition = partition_row[0]
        connection.execute(
            """
            INSERT INTO users (id, email, display_name, password_hash)
            VALUES (%s, 'performance@promptvault.dev', 'Performance Dataset', 'unused')
            ON CONFLICT (id) DO NOTHING
            """,
            (PERFORMANCE_USER_ID,),
        )
        connection.execute(
            """
            INSERT INTO users (id, email, display_name, password_hash)
            VALUES (%s, 'performance-noise@promptvault.dev', 'Performance Noise', 'unused')
            ON CONFLICT (id) DO NOTHING
            """,
            (_DISTRACTOR_USER_ID,),
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, key, owner_id)
            VALUES (%s, 'Performance Dataset', 'performance-dataset', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (PERFORMANCE_PROJECT_ID, PERFORMANCE_USER_ID),
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, key, owner_id)
            VALUES (%s, 'Performance Noise', 'performance-noise', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (_DISTRACTOR_PROJECT_ID, _DISTRACTOR_USER_ID),
        )
        connection.execute(
            """
            INSERT INTO prompts (id, project_id, key, name)
            VALUES (%s, %s, 'representative-prompt', 'Representative Prompt')
            ON CONFLICT (id) DO NOTHING
            """,
            (PERFORMANCE_PROMPT_ID, PERFORMANCE_PROJECT_ID),
        )
        connection.execute(
            """
            INSERT INTO prompts (id, project_id, key, name)
            VALUES (%s, %s, 'noise-prompt', 'Noise Prompt')
            ON CONFLICT (id) DO NOTHING
            """,
            (_DISTRACTOR_PROMPT_ID, _DISTRACTOR_PROJECT_ID),
        )
        connection.execute(
            """INSERT INTO prompt_versions(id,prompt_id,version_number,template_body,
                provider,model,temperature,max_output_tokens,commit_message,created_by)
            VALUES (%s,%s,1,%s,'gemini','gemini-3.5-flash-lite',0,200,'Representative fixture',%s)
            ON CONFLICT (id) DO NOTHING""",
            (PERFORMANCE_VERSION_ID, PERFORMANCE_PROMPT_ID, "Hello {{name}}", PERFORMANCE_USER_ID),
        )
        connection.execute(
            """INSERT INTO prompt_versions(id,prompt_id,version_number,template_body,
                provider,model,temperature,max_output_tokens,commit_message,created_by)
            VALUES (%s,%s,1,%s,'gemini','gemini-3.5-flash-lite',0,200,'Representative fixture',%s)
            ON CONFLICT (id) DO NOTHING""",
            (_DISTRACTOR_VERSION_ID, _DISTRACTOR_PROMPT_ID, "Noise {{name}}", _DISTRACTOR_USER_ID),
        )
        connection.execute(
            "INSERT INTO prompt_version_variables(version_id,ordinal,name) "
            "VALUES (%s,1,'name'),(%s,1,'name') ON CONFLICT DO NOTHING",
            (PERFORMANCE_VERSION_ID, _DISTRACTOR_VERSION_ID),
        )
        target_run_count = max(1, run_count // 20)
        rows = [
            (
                uuid5(_NAMESPACE, f"run-{month_start:%Y-%m}-{index}"),
                PERFORMANCE_USER_ID if index < target_run_count else _DISTRACTOR_USER_ID,
                (PERFORMANCE_VERSION_ID if index < target_run_count else _DISTRACTOR_VERSION_ID),
                f"Hello User {index}",
                index % 100 + 1,
                index % 50 + 1,
                index % 250,
                "0.000123",
                f"performance-{index}",
                month_start + timedelta(seconds=index),
            )
            for index in range(run_count)
        ]
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO runs (
                    id, user_id, version_id, status,
                    output_text, prompt_tokens,
                    completion_tokens, latency_ms, cost, request_id, created_at
                ) VALUES (
                    %s, %s, %s, 'completed',
                    %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (id, created_at) DO NOTHING
                """,
                rows,
            )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO run_inputs(run_id,run_created_at,name,value) "
                "VALUES (%s,%s,'name',%s) ON CONFLICT DO NOTHING",
                [(row[0], row[-1], f"User {index}") for index, row in enumerate(rows)],
            )
        connection.execute("ANALYZE runs")
        connection.execute("ANALYZE prompt_versions")
        connection.execute("ANALYZE prompts")
        persisted_row = connection.execute(
            """
            SELECT count(*) FROM run_context
            WHERE project_id IN (%s, %s) AND created_at >= %s AND created_at < %s
            """,
            (
                PERFORMANCE_PROJECT_ID,
                _DISTRACTOR_PROJECT_ID,
                month_start,
                next_month,
            ),
        ).fetchone()
        if persisted_row is None:
            raise RuntimeError("representative run count returned no row")
        persisted = persisted_row[0]
    # Model the steady-state query workload after bulk fixture loading. PostgreSQL
    # can then use the covering timeline index without random heap reads.
    with psycopg.connect(database_url, autocommit=True) as maintenance:
        maintenance.execute("VACUUM (ANALYZE) runs")
    return {
        "project_id": PERFORMANCE_PROJECT_ID,
        "user_id": PERFORMANCE_USER_ID,
        "prompt_id": PERFORMANCE_PROMPT_ID,
        "version_id": PERFORMANCE_VERSION_ID,
        "run_count": int(persisted),
        "partition": str(partition),
    }

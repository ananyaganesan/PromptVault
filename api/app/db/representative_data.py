"""Deterministic representative data for repeatable query-plan checks."""

from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

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
    month_start = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
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
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            ) VALUES (%s, %s, 1, 'Hello {{name}}', %s, %s, 'Representative version', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                PERFORMANCE_VERSION_ID,
                PERFORMANCE_PROMPT_ID,
                Jsonb(["name"]),
                Jsonb(
                    {
                        "provider": "mock",
                        "model": "deterministic-v1",
                        "temperature": 0,
                        "max_output_tokens": 200,
                    }
                ),
                PERFORMANCE_USER_ID,
            ),
        )
        connection.execute(
            """
            INSERT INTO prompt_versions (
                id, prompt_id, version_number, template_body, variables,
                model_config, commit_message, created_by
            ) VALUES (%s, %s, 1, 'Noise {{name}}', %s, %s, 'Noise version', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                _DISTRACTOR_VERSION_ID,
                _DISTRACTOR_PROMPT_ID,
                Jsonb(["name"]),
                Jsonb(
                    {
                        "provider": "mock",
                        "model": "deterministic-v1",
                        "temperature": 0,
                        "max_output_tokens": 200,
                    }
                ),
                _DISTRACTOR_USER_ID,
            ),
        )
        target_run_count = max(1, run_count // 20)
        rows = [
            (
                uuid5(_NAMESPACE, f"run-{month_start:%Y-%m}-{index}"),
                PERFORMANCE_USER_ID if index < target_run_count else _DISTRACTOR_USER_ID,
                (
                    PERFORMANCE_PROJECT_ID
                    if index < target_run_count
                    else _DISTRACTOR_PROJECT_ID
                ),
                (
                    PERFORMANCE_PROMPT_ID
                    if index < target_run_count
                    else _DISTRACTOR_PROMPT_ID
                ),
                (
                    PERFORMANCE_VERSION_ID
                    if index < target_run_count
                    else _DISTRACTOR_VERSION_ID
                ),
                Jsonb({"name": f"User {index}"}),
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
                    id, user_id, project_id, prompt_id, version_id, status,
                    provider, model, input_variables, output_text, prompt_tokens,
                    completion_tokens, latency_ms, cost, request_id, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'completed', 'mock', 'deterministic-v1',
                    %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (id, created_at) DO NOTHING
                """,
                rows,
            )
        connection.execute("ANALYZE runs")
        persisted_row = connection.execute(
            """
            SELECT count(*) FROM runs
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
    return {
        "project_id": PERFORMANCE_PROJECT_ID,
        "user_id": PERFORMANCE_USER_ID,
        "prompt_id": PERFORMANCE_PROMPT_ID,
        "version_id": PERFORMANCE_VERSION_ID,
        "run_count": int(persisted),
        "partition": str(partition),
    }

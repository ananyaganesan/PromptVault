"""Immutable prompt-version persistence."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.app.schemas.versions import (
    ModelConfiguration,
    PromptVersionResponse,
    VersionAuthorResponse,
)
from api.app.security import UserRole
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

_VERSION_COLUMNS = """
    pv.id, pv.prompt_id, pv.version_number, pv.parent_version_id,
    pv.template_body, pv.variables, pv.model_config, pv.commit_message,
    pv.created_at, creator.id AS creator_id, creator.display_name AS creator_display_name
"""


def _version_from_row(row: Mapping[str, Any]) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=row["id"],
        prompt_id=row["prompt_id"],
        version_number=row["version_number"],
        parent_version_id=row["parent_version_id"],
        template_body=row["template_body"],
        variables=row["variables"],
        model_config=ModelConfiguration.model_validate(row["model_config"]),
        commit_message=row["commit_message"],
        created_by=VersionAuthorResponse(
            id=row["creator_id"],
            display_name=row["creator_display_name"],
        ),
        created_at=row["created_at"],
    )


class VersionRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def create(
        self,
        *,
        prompt_id: UUID,
        parent_version_id: UUID | None,
        template_body: str,
        variables: list[str],
        model_config: ModelConfiguration,
        commit_message: str,
        created_by: UUID,
    ) -> PromptVersionResponse:
        cursor = await self.connection.execute(
            """
            SELECT (create_prompt_version(
                p_prompt_id => %s,
                p_parent_version_id => %s,
                p_template_body => %s,
                p_variables => %s::jsonb,
                p_model_config => %s::jsonb,
                p_commit_message => %s,
                p_created_by => %s
            )).id AS id
            """,
            (
                prompt_id,
                parent_version_id,
                template_body,
                Jsonb(variables),
                Jsonb(model_config.model_dump()),
                commit_message,
                created_by,
            ),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("version function returned no row")
        version = await self.get(row["id"])
        if version is None:
            raise RuntimeError("created version was not returned")
        return version

    async def get(self, version_id: UUID) -> PromptVersionResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_VERSION_COLUMNS}
            FROM prompt_versions pv
            JOIN users creator ON creator.id = pv.created_by
            WHERE pv.id = %s
            """,
            (version_id,),
        )
        row = await cursor.fetchone()
        return _version_from_row(row) if row else None

    async def get_scoped(
        self,
        version_id: UUID,
        user_id: UUID,
        role: UserRole,
    ) -> PromptVersionResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_VERSION_COLUMNS}
            FROM prompt_versions pv
            JOIN prompts p ON p.id = pv.prompt_id
            JOIN users creator ON creator.id = pv.created_by
            WHERE pv.id = %s
              AND (
                  %s = 'admin'
                  OR EXISTS (
                      SELECT 1
                      FROM project_members pm
                      WHERE pm.project_id = p.project_id AND pm.user_id = %s
                  )
              )
            """,
            (version_id, role, user_id),
        )
        row = await cursor.fetchone()
        return _version_from_row(row) if row else None

    async def latest(self, prompt_id: UUID) -> PromptVersionResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_VERSION_COLUMNS}
            FROM prompt_versions pv
            JOIN users creator ON creator.id = pv.created_by
            WHERE pv.prompt_id = %s
            ORDER BY pv.version_number DESC
            LIMIT 1
            """,
            (prompt_id,),
        )
        row = await cursor.fetchone()
        return _version_from_row(row) if row else None

    async def list_for_prompt(
        self,
        prompt_id: UUID,
        *,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> tuple[list[PromptVersionResponse], int]:
        count_cursor = await self.connection.execute(
            "SELECT count(*) AS total FROM prompt_versions WHERE prompt_id = %s",
            (prompt_id,),
        )
        total_row = await count_cursor.fetchone()
        if total_row is None:
            raise RuntimeError("version count returned no row")
        sort_column = {"version_number": "pv.version_number", "created_at": "pv.created_at"}[sort]
        order = "ASC" if direction == "asc" else "DESC"
        cursor = await self.connection.execute(
            f"""
            SELECT {_VERSION_COLUMNS}
            FROM prompt_versions pv
            JOIN users creator ON creator.id = pv.created_by
            WHERE pv.prompt_id = %s
            ORDER BY {sort_column} {order}, pv.id {order}
            LIMIT %s OFFSET %s
            """,
            (prompt_id, page_size, (page - 1) * page_size),
        )
        return [_version_from_row(row) for row in await cursor.fetchall()], int(total_row["total"])

    async def lineage(self, version_id: UUID) -> tuple[list[PromptVersionResponse], bool]:
        cursor = await self.connection.execute(
            f"""
            WITH RECURSIVE ancestry AS (
                SELECT pv.*, ARRAY[pv.id] AS path, 0 AS depth
                FROM prompt_versions pv
                WHERE pv.id = %s
                UNION ALL
                SELECT parent.*, ancestry.path || parent.id, ancestry.depth + 1
                FROM ancestry
                JOIN prompt_versions parent
                  ON parent.id = ancestry.parent_version_id
                 AND NOT parent.id = ANY(ancestry.path)
            )
            SELECT {_VERSION_COLUMNS},
                   (
                       ancestry.parent_version_id IS NOT NULL
                       AND ancestry.parent_version_id = ANY(ancestry.path)
                   ) AS cycle_detected,
                   ancestry.depth
            FROM ancestry
            JOIN prompt_versions pv ON pv.id = ancestry.id
            JOIN users creator ON creator.id = pv.created_by
            ORDER BY ancestry.depth
            """,
            (version_id,),
        )
        rows = await cursor.fetchall()
        return [_version_from_row(row) for row in rows], any(row["cycle_detected"] for row in rows)

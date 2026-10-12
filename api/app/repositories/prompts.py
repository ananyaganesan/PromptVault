"""Prompt metadata persistence."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from api.app.repositories.pagination import read_page
from api.app.schemas.prompts import PromptSummaryResponse
from api.app.security import UserRole
from psycopg import AsyncConnection


def _summary_from_row(row: Mapping[str, Any]) -> PromptSummaryResponse:
    return PromptSummaryResponse(
        id=row["id"],
        project_id=row["project_id"],
        key=row["key"],
        name=row["name"],
        description=row["description"],
        latest_version_number=row["latest_version_number"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PromptRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def create(
        self,
        *,
        project_id: UUID,
        key: str,
        name: str,
        description: str | None,
    ) -> UUID:
        cursor = await self.connection.execute(
            """
            INSERT INTO prompts (project_id, key, name, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, key, name, description),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("prompt insert returned no row")
        return cast(UUID, row["id"])

    async def get_metadata(self, prompt_id: UUID) -> Mapping[str, Any] | None:
        cursor = await self.connection.execute(
            """
            SELECT id, project_id, key, name, description, created_at, updated_at
            FROM prompts
            WHERE id = %s
            """,
            (prompt_id,),
        )
        return await cursor.fetchone()

    async def get_metadata_scoped(
        self, prompt_id: UUID, user_id: UUID, role: UserRole
    ) -> Mapping[str, Any] | None:
        cursor = await self.connection.execute(
            """
            SELECT p.id, p.project_id, p.key, p.name, p.description,
                   p.created_at, p.updated_at
            FROM prompts p
            WHERE p.id = %s
              AND (
                  %s = 'admin'
                  OR EXISTS (
                      SELECT 1
                      FROM project_members pm
                      WHERE pm.project_id = p.project_id AND pm.user_id = %s
                  )
              )
            """,
            (prompt_id, role, user_id),
        )
        return await cursor.fetchone()

    async def lock_member_access(
        self, prompt_id: UUID, user_id: UUID, role: UserRole
    ) -> bool:
        if role == "admin":
            cursor = await self.connection.execute(
                "SELECT id FROM prompts WHERE id = %s FOR KEY SHARE",
                (prompt_id,),
            )
        else:
            cursor = await self.connection.execute(
                """
                SELECT p.id
                FROM prompts p
                JOIN project_members pm
                  ON pm.project_id = p.project_id AND pm.user_id = %s
                WHERE p.id = %s
                FOR KEY SHARE OF p, pm
                """,
                (user_id, prompt_id),
            )
        return await cursor.fetchone() is not None

    async def get_active_versions(self, prompt_id: UUID) -> dict[str, UUID]:
        cursor = await self.connection.execute(
            """
            SELECT environment::text AS environment, version_id
            FROM deployments
            WHERE prompt_id = %s AND status = 'active'
            ORDER BY environment
            """,
            (prompt_id,),
        )
        return {row["environment"]: row["version_id"] for row in await cursor.fetchall()}

    async def list_for_project(
        self,
        project_id: UUID,
        *,
        search: str | None,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> tuple[list[PromptSummaryResponse], int]:
        where = ["p.project_id = %s"]
        parameters: list[Any] = [project_id]
        if search:
            where.append("(p.name ILIKE %s OR p.key ILIKE %s)")
            pattern = f"%{search}%"
            parameters.extend([pattern, pattern])
        where_sql = " AND ".join(where)
        sort_column = {"key": "p.key", "name": "p.name", "updated_at": "p.updated_at"}[sort]
        order = "ASC" if direction == "asc" else "DESC"
        rows, total = await read_page(
            self.connection,
            count_query=f"SELECT count(*) AS total FROM prompts p WHERE {where_sql}",
            items_query=f"""
            SELECT p.id, p.project_id, p.key, p.name, p.description,
                   p.created_at, p.updated_at,
                   latest.version_number AS latest_version_number
            FROM prompts p
            JOIN LATERAL (
                SELECT version_number
                FROM prompt_versions
                WHERE prompt_id = p.id
                ORDER BY version_number DESC
                LIMIT 1
            ) latest ON TRUE
            WHERE {where_sql}
            ORDER BY {sort_column} {order}, p.id {order}
            LIMIT %s OFFSET %s
            """,
            parameters=parameters,
            page=page,
            page_size=page_size,
            order_by=f'{sort_column.removeprefix("p.")} {order}, id {order}',
        )
        return [_summary_from_row(row) for row in rows], total

    async def update(
        self,
        prompt_id: UUID,
        *,
        name_set: bool,
        name: str | None,
        description_set: bool,
        description: str | None,
    ) -> bool:
        assignments: list[str] = []
        parameters: list[Any] = []
        if name_set:
            assignments.append("name = %s")
            parameters.append(name)
        if description_set:
            assignments.append("description = %s")
            parameters.append(description)
        parameters.append(prompt_id)
        cursor = await self.connection.execute(
            f"UPDATE prompts SET {', '.join(assignments)} WHERE id = %s",
            tuple(parameters),
        )
        return cursor.rowcount == 1

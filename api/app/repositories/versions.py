"""Immutable prompt-version persistence."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.app.db.models import ProjectMember, Prompt, User, VersionContext, fields
from api.app.db.orm import ORMConnection, orm_one
from api.app.repositories.pagination import read_page
from api.app.schemas.versions import (
    ModelConfiguration,
    PromptVersionResponse,
    SavedModelConfiguration,
    VersionAuthorResponse,
)
from api.app.security import UserRole
from psycopg.types.json import Jsonb
from sqlalchemy import exists, literal, or_, select

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
        model_config=SavedModelConfiguration.model_validate(row["model_config"]),
        commit_message=row["commit_message"],
        created_by=VersionAuthorResponse(
            id=row["creator_id"],
            display_name=row["creator_display_name"],
        ),
        created_at=row["created_at"],
    )


class VersionRepository:
    def __init__(self, connection: ORMConnection) -> None:
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
        row = await orm_one(
            self.connection,
            select(
                *fields(VersionContext),
                User.id.label("creator_id"),
                User.display_name.label("creator_display_name"),
            )
            .join(User, User.id == VersionContext.created_by)
            .where(VersionContext.id == version_id),
        )
        return _version_from_row(row) if row else None

    async def get_scoped(
        self,
        version_id: UUID,
        user_id: UUID,
        role: UserRole,
    ) -> PromptVersionResponse | None:
        row = await orm_one(
            self.connection,
            select(
                *fields(VersionContext),
                User.id.label("creator_id"),
                User.display_name.label("creator_display_name"),
            )
            .join(User, User.id == VersionContext.created_by)
            .where(VersionContext.id == version_id)
            .join(Prompt, Prompt.id == VersionContext.prompt_id)
            .where(
                or_(
                    literal(role == "admin"),
                    exists().where(
                        ProjectMember.project_id == Prompt.project_id,
                        ProjectMember.user_id == user_id,
                    ),
                )
            ),
        )
        return _version_from_row(row) if row else None

    async def latest(self, prompt_id: UUID) -> PromptVersionResponse | None:
        row = await orm_one(
            self.connection,
            select(
                *fields(VersionContext),
                User.id.label("creator_id"),
                User.display_name.label("creator_display_name"),
            )
            .join(User, User.id == VersionContext.created_by)
            .where(VersionContext.prompt_id == prompt_id)
            .order_by(VersionContext.version_number.desc())
            .limit(1),
        )
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
        sort_column = {"version_number": "pv.version_number", "created_at": "pv.created_at"}[sort]
        order = "ASC" if direction == "asc" else "DESC"
        rows, total = await read_page(
            self.connection,
            count_query="SELECT count(*) AS total FROM version_context WHERE prompt_id = %s",
            items_query=f"""
            SELECT {_VERSION_COLUMNS}
            FROM version_context pv
            JOIN users creator ON creator.id = pv.created_by
            WHERE pv.prompt_id = %s
            ORDER BY {sort_column} {order}, pv.id {order}
            LIMIT %s OFFSET %s
            """,
            parameters=(prompt_id,),
            page=page,
            page_size=page_size,
            order_by=f"{sort_column.removeprefix('pv.')} {order}, id {order}",
        )
        return [_version_from_row(row) for row in rows], total

    async def lineage(self, version_id: UUID) -> tuple[list[PromptVersionResponse], bool]:
        cursor = await self.connection.execute(
            f"""
            WITH RECURSIVE ancestry AS (
                SELECT pv.*, ARRAY[pv.id] AS path, 0 AS depth
                FROM version_context pv
                WHERE pv.id = %s
                UNION ALL
                SELECT parent.*, ancestry.path || parent.id, ancestry.depth + 1
                FROM ancestry
                JOIN version_context parent
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
            JOIN version_context pv ON pv.id = ancestry.id
            JOIN users creator ON creator.id = pv.created_by
            ORDER BY ancestry.depth
            """,
            (version_id,),
        )
        rows = await cursor.fetchall()
        return [_version_from_row(row) for row in rows], any(row["cycle_detected"] for row in rows)

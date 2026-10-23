"""Prompt metadata persistence."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from api.app.db.models import DeploymentContext, ProjectMember, Prompt, fields
from api.app.db.orm import ORMConnection, orm_all, orm_one
from api.app.repositories.pagination import read_page
from api.app.schemas.prompts import PromptSummaryResponse
from api.app.security import UserRole
from sqlalchemy import exists, insert, literal, or_, select, update


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
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def create(
        self,
        *,
        project_id: UUID,
        key: str,
        name: str,
        description: str | None,
    ) -> UUID:
        row = await orm_one(
            self.connection,
            insert(Prompt)
            .values(project_id=project_id, key=key, name=name, description=description)
            .returning(Prompt.id),
        )
        if row is None:
            raise RuntimeError("prompt insert returned no row")
        return cast(UUID, row["id"])

    async def get_metadata(self, prompt_id: UUID) -> Mapping[str, Any] | None:
        return await orm_one(self.connection, select(*fields(Prompt)).where(Prompt.id == prompt_id))

    async def get_metadata_scoped(
        self, prompt_id: UUID, user_id: UUID, role: UserRole
    ) -> Mapping[str, Any] | None:
        member = exists().where(
            ProjectMember.project_id == Prompt.project_id, ProjectMember.user_id == user_id
        )
        return await orm_one(
            self.connection,
            select(*fields(Prompt)).where(
                Prompt.id == prompt_id, or_(literal(role == "admin"), member)
            ),
        )

    async def lock_member_access(self, prompt_id: UUID, user_id: UUID, role: UserRole) -> bool:
        statement = select(Prompt.id).where(Prompt.id == prompt_id)
        if role == "admin":
            statement = statement.with_for_update(read=True, key_share=True, of=Prompt)
        else:
            statement = (
                statement.join(ProjectMember, ProjectMember.project_id == Prompt.project_id)
                .where(ProjectMember.user_id == user_id)
                .with_for_update(read=True, key_share=True, of=(Prompt, ProjectMember))
            )
        return await orm_one(self.connection, statement) is not None

    async def get_active_versions(self, prompt_id: UUID) -> dict[str, UUID]:
        rows = await orm_all(
            self.connection,
            select(DeploymentContext.environment, DeploymentContext.version_id)
            .where(DeploymentContext.prompt_id == prompt_id, DeploymentContext.status == "active")
            .order_by(DeploymentContext.environment),
        )
        return {row["environment"]: row["version_id"] for row in rows}

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
            order_by=f"{sort_column.removeprefix('p.')} {order}, id {order}",
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
        values = {}
        if name_set:
            values["name"] = name
        if description_set:
            values["description"] = description
        row = await orm_one(
            self.connection,
            update(Prompt).where(Prompt.id == prompt_id).values(**values).returning(Prompt.id),
        )
        return row is not None

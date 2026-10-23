"""Project and membership persistence."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from api.app.db.models import Project, ProjectInvitation, ProjectMember, Prompt, User, fields
from api.app.db.orm import ORMConnection, execute_orm, orm_all, orm_one
from api.app.repositories.pagination import read_page
from api.app.schemas.projects import (
    ProjectInvitationResponse,
    ProjectMemberResponse,
    ProjectOwnerResponse,
    ProjectResponse,
)
from api.app.security import UserRole
from sqlalchemy import delete, func, insert, select, update

_PROJECT_COLUMNS = """
    p.id, p.name, p.key, p.description, p.created_at, p.updated_at,
    owner.id AS owner_id, owner.display_name AS owner_display_name,
    (SELECT count(*) FROM project_members pm WHERE pm.project_id = p.id) AS member_count,
    (SELECT count(*) FROM prompts pr WHERE pr.project_id = p.id) AS prompt_count
"""


def _project_from_row(row: Mapping[str, Any]) -> ProjectResponse:
    return ProjectResponse(
        id=row["id"],
        name=row["name"],
        key=row["key"],
        description=row["description"],
        owner=ProjectOwnerResponse(
            id=row["owner_id"],
            display_name=row["owner_display_name"],
        ),
        member_count=row["member_count"],
        prompt_count=row["prompt_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def set_audit_context(self, user_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), set_config('app.request_id', %s, true)",
            (str(user_id), request_id),
        )

    async def lock_member_access(self, project_id: UUID, user_id: UUID, role: UserRole) -> bool:
        statement = select(Project.id).where(Project.id == project_id)
        if role == "admin":
            statement = statement.with_for_update(read=True, key_share=True, of=Project)
        else:
            statement = (
                statement.join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == user_id)
                .with_for_update(read=True, key_share=True, of=(Project, ProjectMember))
            )
        return await orm_one(self.connection, statement) is not None

    async def lock_owner_access(self, project_id: UUID, user_id: UUID, role: UserRole) -> bool:
        statement = select(Project.id).where(Project.id == project_id)
        if role == "admin":
            statement = statement.with_for_update(read=True, key_share=True, of=Project)
        else:
            statement = (
                statement.join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == user_id, Project.owner_id == user_id)
                .with_for_update(read=True, key_share=True, of=(Project, ProjectMember))
            )
        return await orm_one(self.connection, statement) is not None

    async def create(
        self,
        *,
        name: str,
        key: str,
        description: str | None,
        owner_id: UUID,
    ) -> UUID:
        row = await orm_one(
            self.connection,
            insert(Project)
            .values(name=name, key=key, description=description, owner_id=owner_id)
            .returning(Project.id),
        )
        if row is None:
            raise RuntimeError("project insert returned no row")
        return cast(UUID, row["id"])

    async def get(self, project_id: UUID) -> ProjectResponse | None:
        members = (
            select(func.count())
            .where(ProjectMember.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        prompts = (
            select(func.count())
            .where(Prompt.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        row = await orm_one(
            self.connection,
            select(
                Project.id,
                Project.name,
                Project.key,
                Project.description,
                Project.created_at,
                Project.updated_at,
                User.id.label("owner_id"),
                User.display_name.label("owner_display_name"),
                members.label("member_count"),
                prompts.label("prompt_count"),
            )
            .join(User, User.id == Project.owner_id)
            .where(Project.id == project_id),
        )
        return _project_from_row(row) if row else None

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        search: str | None,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> tuple[list[ProjectResponse], int]:
        where = [
            """(%s = 'admin' OR EXISTS (
                SELECT 1 FROM project_members scope
                WHERE scope.project_id = p.id AND scope.user_id = %s
            ))"""
        ]
        parameters: list[Any] = [role, user_id]
        if search:
            where.append("(p.name ILIKE %s OR p.key ILIKE %s)")
            pattern = f"%{search}%"
            parameters.extend([pattern, pattern])
        where_sql = " AND ".join(where)
        sort_column = {
            "name": "p.name",
            "created_at": "p.created_at",
            "updated_at": "p.updated_at",
        }[sort]
        order = "ASC" if direction == "asc" else "DESC"
        rows, total = await read_page(
            self.connection,
            count_query=f"SELECT count(*) AS total FROM projects p WHERE {where_sql}",
            items_query=f"""
            SELECT {_PROJECT_COLUMNS}
            FROM projects p
            JOIN users owner ON owner.id = p.owner_id
            WHERE {where_sql}
            ORDER BY {sort_column} {order}, p.id {order}
            LIMIT %s OFFSET %s
            """,
            parameters=parameters,
            page=page,
            page_size=page_size,
            order_by=f"{sort_column.removeprefix('p.')} {order}, id {order}",
        )
        return [_project_from_row(row) for row in rows], total

    async def update(
        self,
        project_id: UUID,
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
        return (
            await orm_one(
                self.connection,
                update(Project)
                .where(Project.id == project_id)
                .values(**values)
                .returning(Project.id),
            )
            is not None
        )

    async def delete(self, project_id: UUID, actor_id: UUID, request_id: str) -> bool:
        cursor = await self.connection.execute(
            "SELECT delete_project(%s, %s, %s) AS deleted",
            (project_id, actor_id, request_id),
        )
        row = await cursor.fetchone()
        return bool(row and row["deleted"])

    async def list_members(
        self, project_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[ProjectMemberResponse], int]:
        rows, total = await read_page(
            self.connection,
            count_query="SELECT count(*) AS total FROM project_members WHERE project_id = %s",
            items_query="""
            SELECT u.id, u.email, u.display_name, u.role, u.is_active, u.created_at,
                   (p.owner_id = u.id) AS is_owner
            FROM project_members pm
            JOIN users u ON u.id = pm.user_id
            JOIN projects p ON p.id = pm.project_id
            WHERE pm.project_id = %s
            ORDER BY (p.owner_id = u.id) DESC, u.display_name ASC, u.id ASC
            LIMIT %s OFFSET %s
            """,
            parameters=(project_id,),
            page=page,
            page_size=page_size,
            order_by="is_owner DESC, display_name ASC, id ASC",
        )
        items = [ProjectMemberResponse.model_validate(row) for row in rows]
        return items, total

    async def add_member(self, project_id: UUID, user_id: UUID, added_by: UUID) -> None:
        await execute_orm(
            self.connection,
            insert(ProjectMember).values(project_id=project_id, user_id=user_id, added_by=added_by),
        )

    async def get_member(self, project_id: UUID, user_id: UUID) -> ProjectMemberResponse | None:
        row = await orm_one(
            self.connection,
            select(
                User.id,
                User.email,
                User.display_name,
                User.role,
                User.is_active,
                User.created_at,
                (Project.owner_id == User.id).label("is_owner"),
            )
            .select_from(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id),
        )
        return ProjectMemberResponse.model_validate(row) if row else None

    async def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        return (
            await orm_one(
                self.connection,
                delete(ProjectMember)
                .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
                .returning(ProjectMember.user_id),
            )
            is not None
        )

    async def create_invitation(
        self, project_id: UUID, user_id: UUID, invited_by: UUID, token_hash: str
    ) -> UUID:
        # Allow a fresh invitation after expiry while retaining its audit history.
        await execute_orm(
            self.connection,
            update(ProjectInvitation)
            .where(
                ProjectInvitation.project_id == project_id,
                ProjectInvitation.user_id == user_id,
                ProjectInvitation.accepted_at.is_(None),
                ProjectInvitation.revoked_at.is_(None),
                ProjectInvitation.expires_at <= func.clock_timestamp(),
            )
            .values(revoked_at=func.clock_timestamp()),
        )
        row = await orm_one(
            self.connection,
            insert(ProjectInvitation)
            .values(
                project_id=project_id,
                user_id=user_id,
                invited_by=invited_by,
                token_hash=token_hash,
                expires_at=func.current_timestamp() + timedelta(days=7),
            )
            .returning(ProjectInvitation.id),
        )
        assert row is not None
        return cast(UUID, row["id"])

    async def list_invitations(self, project_id: UUID) -> list[ProjectInvitationResponse]:
        rows = await orm_all(
            self.connection,
            select(
                ProjectInvitation.id,
                ProjectInvitation.project_id,
                User.email,
                User.display_name,
                ProjectInvitation.created_at,
                ProjectInvitation.expires_at,
            )
            .join(User, User.id == ProjectInvitation.user_id)
            .where(
                ProjectInvitation.project_id == project_id,
                ProjectInvitation.accepted_at.is_(None),
                ProjectInvitation.revoked_at.is_(None),
            )
            .order_by(ProjectInvitation.created_at.desc(), ProjectInvitation.id),
        )
        return [ProjectInvitationResponse.model_validate(row) for row in rows]

    async def revoke_invitation(self, project_id: UUID, invitation_id: UUID) -> bool:
        return (
            await orm_one(
                self.connection,
                update(ProjectInvitation)
                .where(
                    ProjectInvitation.project_id == project_id,
                    ProjectInvitation.id == invitation_id,
                    ProjectInvitation.accepted_at.is_(None),
                    ProjectInvitation.revoked_at.is_(None),
                )
                .values(revoked_at=func.clock_timestamp())
                .returning(ProjectInvitation.id),
            )
            is not None
        )

    async def lock_invitation(self, token_hash: str) -> dict[str, Any] | None:
        return await orm_one(
            self.connection,
            select(
                *fields(ProjectInvitation),
                (ProjectInvitation.expires_at > func.clock_timestamp()).label("unexpired"),
            )
            .where(ProjectInvitation.token_hash == token_hash)
            .with_for_update(),
        )

    async def consume_invitation(self, invitation_id: UUID) -> None:
        await execute_orm(
            self.connection,
            update(ProjectInvitation)
            .where(ProjectInvitation.id == invitation_id)
            .values(accepted_at=func.clock_timestamp()),
        )

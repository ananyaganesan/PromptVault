"""Project and membership persistence."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from api.app.repositories.pagination import read_page
from api.app.schemas.projects import (
    ProjectInvitationResponse,
    ProjectMemberResponse,
    ProjectOwnerResponse,
    ProjectResponse,
)
from api.app.security import UserRole
from psycopg import AsyncConnection

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
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def set_audit_context(self, user_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), set_config('app.request_id', %s, true)",
            (str(user_id), request_id),
        )

    async def lock_member_access(self, project_id: UUID, user_id: UUID, role: UserRole) -> bool:
        if role == "admin":
            cursor = await self.connection.execute(
                "SELECT id FROM projects WHERE id = %s FOR KEY SHARE",
                (project_id,),
            )
        else:
            cursor = await self.connection.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN project_members pm
                  ON pm.project_id = p.id AND pm.user_id = %s
                WHERE p.id = %s
                FOR KEY SHARE OF p, pm
                """,
                (user_id, project_id),
            )
        return await cursor.fetchone() is not None

    async def lock_owner_access(self, project_id: UUID, user_id: UUID, role: UserRole) -> bool:
        if role == "admin":
            cursor = await self.connection.execute(
                "SELECT id FROM projects WHERE id = %s FOR KEY SHARE",
                (project_id,),
            )
        else:
            cursor = await self.connection.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN project_members pm
                  ON pm.project_id = p.id AND pm.user_id = %s
                WHERE p.id = %s AND p.owner_id = %s
                FOR KEY SHARE OF p, pm
                """,
                (user_id, project_id, user_id),
            )
        return await cursor.fetchone() is not None

    async def create(
        self,
        *,
        name: str,
        key: str,
        description: str | None,
        owner_id: UUID,
    ) -> UUID:
        cursor = await self.connection.execute(
            """
            INSERT INTO projects (name, key, description, owner_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (name, key, description, owner_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("project insert returned no row")
        return cast(UUID, row["id"])

    async def get(self, project_id: UUID) -> ProjectResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_PROJECT_COLUMNS}
            FROM projects p
            JOIN users owner ON owner.id = p.owner_id
            WHERE p.id = %s
            """,
            (project_id,),
        )
        row = await cursor.fetchone()
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
        assignments: list[str] = []
        parameters: list[Any] = []
        if name_set:
            assignments.append("name = %s")
            parameters.append(name)
        if description_set:
            assignments.append("description = %s")
            parameters.append(description)
        parameters.append(project_id)
        cursor = await self.connection.execute(
            f"UPDATE projects SET {', '.join(assignments)} WHERE id = %s",
            tuple(parameters),
        )
        return cursor.rowcount == 1

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
        await self.connection.execute(
            """
            INSERT INTO project_members (project_id, user_id, added_by)
            VALUES (%s, %s, %s)
            """,
            (project_id, user_id, added_by),
        )

    async def get_member(self, project_id: UUID, user_id: UUID) -> ProjectMemberResponse | None:
        cursor = await self.connection.execute(
            """
            SELECT u.id, u.email, u.display_name, u.role, u.is_active, u.created_at,
                   (p.owner_id = u.id) AS is_owner
            FROM project_members pm
            JOIN users u ON u.id = pm.user_id
            JOIN projects p ON p.id = pm.project_id
            WHERE pm.project_id = %s AND pm.user_id = %s
            """,
            (project_id, user_id),
        )
        row = await cursor.fetchone()
        return ProjectMemberResponse.model_validate(row) if row else None

    async def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        cursor = await self.connection.execute(
            "DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
            (project_id, user_id),
        )
        return cursor.rowcount == 1

    async def create_invitation(
        self, project_id: UUID, user_id: UUID, invited_by: UUID, token_hash: str
    ) -> UUID:
        # Allow a fresh invitation after expiry while retaining its audit history.
        await self.connection.execute(
            """UPDATE project_invitations SET revoked_at = clock_timestamp()
            WHERE project_id = %s AND user_id = %s AND accepted_at IS NULL
              AND revoked_at IS NULL AND expires_at <= clock_timestamp()""",
            (project_id, user_id),
        )
        cursor = await self.connection.execute(
            """INSERT INTO project_invitations
            (project_id, user_id, invited_by, token_hash, expires_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '7 days') RETURNING id""",
            (project_id, user_id, invited_by, token_hash),
        )
        row = await cursor.fetchone()
        assert row is not None
        return cast(UUID, row["id"])

    async def list_invitations(self, project_id: UUID) -> list[ProjectInvitationResponse]:
        cursor = await self.connection.execute(
            """SELECT i.id, i.project_id, u.email, u.display_name, i.created_at, i.expires_at
            FROM project_invitations i JOIN users u ON u.id = i.user_id
            WHERE i.project_id = %s AND i.accepted_at IS NULL AND i.revoked_at IS NULL
            ORDER BY i.created_at DESC, i.id""",
            (project_id,),
        )
        return [ProjectInvitationResponse.model_validate(row) for row in await cursor.fetchall()]

    async def revoke_invitation(self, project_id: UUID, invitation_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """UPDATE project_invitations SET revoked_at = clock_timestamp()
            WHERE project_id = %s AND id = %s AND accepted_at IS NULL AND revoked_at IS NULL""",
            (project_id, invitation_id),
        )
        return cursor.rowcount == 1

    async def lock_invitation(self, token_hash: str) -> dict[str, Any] | None:
        cursor = await self.connection.execute(
            """SELECT i.*, (i.expires_at > clock_timestamp()) AS unexpired
            FROM project_invitations i WHERE token_hash = %s FOR UPDATE""",
            (token_hash,),
        )
        return await cursor.fetchone()

    async def consume_invitation(self, invitation_id: UUID) -> None:
        await self.connection.execute(
            "UPDATE project_invitations SET accepted_at = clock_timestamp() WHERE id = %s",
            (invitation_id,),
        )

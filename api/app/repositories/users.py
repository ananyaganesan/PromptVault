"""Parameterized user and project-scope queries."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from api.app.schemas.users import UserRole
from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: UUID
    email: str
    display_name: str
    password_hash: str
    role: UserRole
    is_active: bool
    created_at: datetime


def _user_from_row(row: Mapping[str, Any]) -> UserRecord:
    return UserRecord(
        id=cast(UUID, row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        password_hash=str(row["password_hash"]),
        role=cast(UserRole, row["role"]),
        is_active=bool(row["is_active"]),
        created_at=cast(datetime, row["created_at"]),
    )


class UserRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> UserRecord:
        cursor = await self.connection.execute(
            """
            INSERT INTO users (email, display_name, password_hash, role)
            VALUES (%s, %s, %s, 'user')
            RETURNING id, email, display_name, password_hash, role, is_active, created_at
            """,
            (email, display_name, password_hash),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("user insert returned no row")
        return _user_from_row(row)

    async def get_by_email(self, email: str) -> UserRecord | None:
        cursor = await self.connection.execute(
            """
            SELECT id, email, display_name, password_hash, role, is_active, created_at
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        row = await cursor.fetchone()
        return _user_from_row(row) if row is not None else None

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        cursor = await self.connection.execute(
            """
            SELECT id, email, display_name, password_hash, role, is_active, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return _user_from_row(row) if row is not None else None

    async def create_password_reset_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        # Use the same lock order as reset confirmation: user before token.
        await self.connection.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
        await self.connection.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = %s AND used_at IS NULL",
            (user_id,),
        )
        await self.connection.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )

    async def lock_password_reset_user(self, token_hash: str) -> UserRecord | None:
        cursor = await self.connection.execute(
            """
            SELECT u.id, u.email, u.display_name, u.password_hash, u.role,
                   u.is_active, u.created_at
            FROM users u
            JOIN password_reset_tokens t ON t.user_id = u.id
            WHERE t.token_hash = %s AND t.used_at IS NULL
              AND t.expires_at > clock_timestamp() AND u.is_active
            FOR UPDATE OF u
            """,
            (token_hash,),
        )
        row = await cursor.fetchone()
        return _user_from_row(row) if row is not None else None

    async def password_history(self, user_id: UUID) -> list[str]:
        cursor = await self.connection.execute(
            "SELECT password_hash FROM password_history WHERE user_id = %s",
            (user_id,),
        )
        return [str(row["password_hash"]) for row in await cursor.fetchall()]

    async def consume_password_reset_token(self, *, token_hash: str, password_hash: str) -> bool:
        cursor = await self.connection.execute(
            """
            WITH consumed_token AS (
                UPDATE password_reset_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE token_hash = %s
                  AND used_at IS NULL
                  AND expires_at > clock_timestamp()
                RETURNING user_id
            )
            UPDATE users
            SET password_hash = %s,
                updated_at = CURRENT_TIMESTAMP
            FROM consumed_token
            WHERE users.id = consumed_token.user_id
            RETURNING users.id
            """,
            (token_hash, password_hash),
        )
        return await cursor.fetchone() is not None

    async def is_project_member(self, user_id: UUID, project_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM project_members
                WHERE project_id = %s AND user_id = %s
            ) AS allowed
            """,
            (project_id, user_id),
        )
        row = await cursor.fetchone()
        return bool(row and row["allowed"])

    async def is_project_owner(self, user_id: UUID, project_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM projects
                WHERE id = %s AND owner_id = %s
            ) AS allowed
            """,
            (project_id, user_id),
        )
        row = await cursor.fetchone()
        return bool(row and row["allowed"])

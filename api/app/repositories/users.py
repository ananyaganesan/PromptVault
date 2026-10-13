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
    email_verified_at: datetime | None
    created_at: datetime


def _user_from_row(row: Mapping[str, Any]) -> UserRecord:
    return UserRecord(
        id=cast(UUID, row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"]),
        password_hash=str(row["password_hash"]),
        role=cast(UserRole, row["role"]),
        is_active=bool(row["is_active"]),
        email_verified_at=cast(datetime | None, row["email_verified_at"]),
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
            RETURNING id, email, display_name, password_hash, role, is_active,
                      email_verified_at, created_at
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
            SELECT id, email, display_name, password_hash, role, is_active,
                   email_verified_at, created_at
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
            SELECT id, email, display_name, password_hash, role, is_active,
                   email_verified_at, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return _user_from_row(row) if row is not None else None

    async def update_display_name(
        self,
        user_id: UUID,
        session_id: UUID,
        display_name: str,
        request_id: str,
    ) -> UserRecord:
        cursor = await self.connection.execute(
            "SELECT * FROM update_self_display_name(%s, %s, %s, %s)",
            (user_id, session_id, display_name, request_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("profile update returned no row")
        return _user_from_row(row)

    async def create_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        await self.connection.execute(
            """
            INSERT INTO auth_sessions (id, user_id, issued_at, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (session_id, user_id, issued_at, expires_at),
        )

    async def is_session_active(self, session_id: UUID, user_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM auth_sessions
                WHERE id = %s AND user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > clock_timestamp()
            ) AS active
            """,
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        return bool(row and row["active"])

    async def revoke_session(self, session_id: UUID, user_id: UUID) -> None:
        await self.connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = CURRENT_TIMESTAMP, revocation_reason = 'logout'
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            """,
            (session_id, user_id),
        )

    async def export_account(self, user_id: UUID) -> dict[str, list[dict[str, Any]]]:
        queries = {
            "owned_projects": """
                SELECT id, name, key, description, created_at, updated_at
                FROM projects WHERE owner_id = %s ORDER BY created_at, id
            """,
            "memberships": """
                SELECT project_id, created_at FROM project_members
                WHERE user_id = %s ORDER BY created_at, project_id
            """,
            "prompt_versions": """
                SELECT id, prompt_id, version_number, parent_version_id, template_body,
                       variables, model_config, commit_message, created_at
                FROM prompt_versions WHERE created_by = %s ORDER BY created_at, id
            """,
            "runs": """
                SELECT id, project_id, prompt_id, version_id, status, provider, model,
                       input_variables, output_text, prompt_tokens, completion_tokens,
                       latency_ms, cost, error_code, created_at
                FROM runs WHERE user_id = %s ORDER BY created_at, id
            """,
            "deployments": """
                SELECT id, prompt_id, version_id, environment, status, request_note,
                       review_note, rollback_reason, rollback_of_id, requested_at,
                       reviewed_at, activated_at
                FROM deployments WHERE requested_by = %s OR reviewed_by = %s
                ORDER BY requested_at, id
            """,
            "api_tokens": """
                SELECT id, project_id, name, token_prefix, created_at, expires_at, revoked_at
                FROM api_tokens WHERE created_by = %s ORDER BY created_at, id
            """,
        }
        exported: dict[str, list[dict[str, Any]]] = {}
        for name, query in queries.items():
            parameters = (user_id, user_id) if name == "deployments" else (user_id,)
            cursor = await self.connection.execute(query, parameters)
            exported[name] = [dict(row) for row in await cursor.fetchall()]
        return exported

    async def close_account(self, *, user_id: UUID, password_hash: str, request_id: str) -> bool:
        cursor = await self.connection.execute(
            "SELECT close_user_account(%s, %s, %s) AS closed",
            (user_id, password_hash, request_id),
        )
        row = await cursor.fetchone()
        return bool(row and row["closed"])

    async def create_password_reset_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
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

    async def create_email_verification_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        await self.connection.execute(
            """
            INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )

    async def confirm_email_verification(self, token_hash: str) -> bool:
        cursor = await self.connection.execute(
            "SELECT confirm_email_verification(%s) AS confirmed",
            (token_hash,),
        )
        row = await cursor.fetchone()
        return bool(row and row["confirmed"])

    async def lock_password_reset_user(self, token_hash: str) -> UserRecord | None:
        cursor = await self.connection.execute(
            """
            SELECT u.id, u.email, u.display_name, u.password_hash, u.role,
                   u.is_active, u.email_verified_at, u.created_at
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
            "SELECT consume_password_reset_token(%s, %s) AS consumed",
            (token_hash, password_hash),
        )
        row = await cursor.fetchone()
        return bool(row and row["consumed"])

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

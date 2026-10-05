"""Runtime token persistence without plaintext storage."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from api.app.schemas.tokens import ApiTokenResponse, ServePromptResponse
from api.app.schemas.versions import ModelConfiguration
from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class RuntimeTokenRecord:
    id: UUID
    project_id: UUID


def _token_from_row(row: Mapping[str, Any]) -> ApiTokenResponse:
    return ApiTokenResponse(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        token_prefix=row["token_prefix"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


class TokenRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def set_audit_context(self, actor_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), "
            "set_config('app.request_id', %s, true)",
            (str(actor_id), request_id),
        )

    async def is_owner(self, project_id: UUID, actor_id: UUID, is_admin: bool) -> bool:
        cursor = await self.connection.execute(
            "SELECT EXISTS (SELECT 1 FROM projects WHERE id = %s "
            "AND (owner_id = %s OR %s)) AS allowed",
            (project_id, actor_id, is_admin),
        )
        row = await cursor.fetchone()
        return bool(row and row["allowed"])

    async def create(
        self,
        *,
        project_id: UUID,
        name: str,
        token_prefix: str,
        token_hash: str,
        created_by: UUID,
        expires_at: datetime | None,
    ) -> ApiTokenResponse:
        cursor = await self.connection.execute(
            """
            INSERT INTO api_tokens (
                project_id, name, token_prefix, token_hash, created_by, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, project_id, name, token_prefix, created_by,
                      created_at, expires_at, revoked_at
            """,
            (project_id, name, token_prefix, token_hash, created_by, expires_at),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("token insert returned no row")
        return _token_from_row(row)

    async def list_scoped(
        self,
        *,
        actor_id: UUID,
        is_admin: bool,
        project_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ApiTokenResponse], int]:
        where = "(%s OR p.owner_id = %s)"
        parameters: list[Any] = [is_admin, actor_id]
        if project_id is not None:
            where += " AND t.project_id = %s"
            parameters.append(project_id)
        count_cursor = await self.connection.execute(
            f"""SELECT count(*) AS total FROM api_tokens t
                JOIN projects p ON p.id = t.project_id WHERE {where}""",
            tuple(parameters),
        )
        total_row = await count_cursor.fetchone()
        if total_row is None:
            raise RuntimeError("token count returned no row")
        cursor = await self.connection.execute(
            f"""
            SELECT t.id, t.project_id, t.name, t.token_prefix, t.created_by,
                   t.created_at, t.expires_at, t.revoked_at
            FROM api_tokens t
            JOIN projects p ON p.id = t.project_id
            WHERE {where}
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, page_size, (page - 1) * page_size),
        )
        return [_token_from_row(row) for row in await cursor.fetchall()], int(total_row["total"])

    async def project_id_for_token(self, token_id: UUID) -> UUID | None:
        cursor = await self.connection.execute(
            "SELECT project_id FROM api_tokens WHERE id = %s", (token_id,)
        )
        row = await cursor.fetchone()
        return row["project_id"] if row else None

    async def revoke(self, token_id: UUID, actor_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """UPDATE api_tokens SET revoked_at = CURRENT_TIMESTAMP, revoked_by = %s
               WHERE id = %s AND revoked_at IS NULL RETURNING id""",
            (actor_id, token_id),
        )
        return await cursor.fetchone() is not None

    async def authenticate(self, token_hash: str) -> RuntimeTokenRecord | None:
        cursor = await self.connection.execute(
            """
            SELECT id, project_id FROM api_tokens
            WHERE token_hash = %s AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
            (token_hash,),
        )
        row = await cursor.fetchone()
        return RuntimeTokenRecord(id=row["id"], project_id=row["project_id"]) if row else None

    async def served_prompt(
        self, project_id: UUID, key: str, environment: str
    ) -> tuple[ServePromptResponse, UUID] | None:
        cursor = await self.connection.execute(
            """
            SELECT p.project_id, p.key AS prompt_key, d.environment,
                   pv.id AS version_id, pv.version_number, pv.template_body,
                   pv.variables, pv.model_config, d.activated_at, d.id AS deployment_id
            FROM prompts p
            JOIN deployments d ON d.prompt_id = p.id
            JOIN prompt_versions pv ON pv.id = d.version_id
            WHERE p.project_id = %s AND p.key = %s
              AND d.environment = %s AND d.status = 'active'
            """,
            (project_id, key, environment),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        from api.app.schemas.tokens import ServedVersion

        return (
            ServePromptResponse(
                project_id=row["project_id"],
                prompt_key=row["prompt_key"],
                environment=row["environment"],
                version=ServedVersion(id=row["version_id"], version_number=row["version_number"]),
                template_body=row["template_body"],
                variables=row["variables"],
                model_config=ModelConfiguration.model_validate(row["model_config"]),
                activated_at=row["activated_at"],
            ),
            row["deployment_id"],
        )

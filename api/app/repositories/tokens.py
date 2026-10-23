"""Runtime token persistence without plaintext storage."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from api.app.db.models import ApiToken, Project, fields
from api.app.db.orm import ORMConnection, orm_one, orm_page
from api.app.schemas.tokens import ApiTokenResponse, ServePromptResponse
from api.app.schemas.versions import SavedModelConfiguration
from sqlalchemy import exists, func, insert, literal, or_, select, update


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
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def set_audit_context(self, actor_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), set_config('app.request_id', %s, true)",
            (str(actor_id), request_id),
        )

    async def is_owner(self, project_id: UUID, actor_id: UUID, is_admin: bool) -> bool:
        row = await orm_one(
            self.connection,
            select(
                exists()
                .where(
                    Project.id == project_id, or_(Project.owner_id == actor_id, literal(is_admin))
                )
                .label("allowed")
            ),
        )
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
        row = await orm_one(
            self.connection,
            insert(ApiToken)
            .values(
                project_id=project_id,
                name=name,
                token_prefix=token_prefix,
                token_hash=token_hash,
                created_by=created_by,
                expires_at=expires_at,
            )
            .returning(*fields(ApiToken)),
        )
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
        statement = (
            select(
                ApiToken.id,
                ApiToken.project_id,
                ApiToken.name,
                ApiToken.token_prefix,
                ApiToken.created_by,
                ApiToken.created_at,
                ApiToken.expires_at,
                ApiToken.revoked_at,
            )
            .join(Project, Project.id == ApiToken.project_id)
            .where(or_(literal(is_admin), Project.owner_id == actor_id))
        )
        if project_id is not None:
            statement = statement.where(ApiToken.project_id == project_id)
        rows, total = await orm_page(
            self.connection,
            statement.order_by(ApiToken.created_at.desc(), ApiToken.id.desc()),
            page=page,
            page_size=page_size,
            order=[("created_at", True), ("id", True)],
        )
        return [_token_from_row(row) for row in rows], total

    async def project_id_for_token(self, token_id: UUID) -> UUID | None:
        row = await orm_one(
            self.connection, select(ApiToken.project_id).where(ApiToken.id == token_id)
        )
        return row["project_id"] if row else None

    async def revoke(self, token_id: UUID, actor_id: UUID) -> bool:
        return (
            await orm_one(
                self.connection,
                update(ApiToken)
                .where(ApiToken.id == token_id, ApiToken.revoked_at.is_(None))
                .values(revoked_at=func.current_timestamp(), revoked_by=actor_id)
                .returning(ApiToken.id),
            )
            is not None
        )

    async def authenticate(self, token_hash: str) -> RuntimeTokenRecord | None:
        row = await orm_one(
            self.connection,
            select(ApiToken.id, ApiToken.project_id).where(
                ApiToken.token_hash == token_hash,
                ApiToken.revoked_at.is_(None),
                or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > func.current_timestamp()),
            ),
        )
        return RuntimeTokenRecord(**row) if row else None

    async def served_prompt(
        self, project_id: UUID, key: str, environment: str
    ) -> tuple[ServePromptResponse, UUID] | None:
        cursor = await self.connection.execute(
            """
            SELECT p.project_id, p.key AS prompt_key, d.environment,
                   pv.id AS version_id, pv.version_number, pv.template_body,
                   pv.variables, pv.model_config, d.activated_at, d.id AS deployment_id
            FROM prompts p
            JOIN deployment_context d ON d.prompt_id = p.id
            JOIN version_context pv ON pv.id = d.version_id
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
                model_config=SavedModelConfiguration.model_validate(row["model_config"]),
                activated_at=row["activated_at"],
            ),
            row["deployment_id"],
        )

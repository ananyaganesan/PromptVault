"""Parameterized user and project-scope queries."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, cast
from uuid import UUID

from api.app.db.models import (
    ApiToken,
    AuthSession,
    DeploymentContext,
    EmailVerificationToken,
    PasswordHistory,
    PasswordResetToken,
    Project,
    ProjectMember,
    RunContext,
    User,
    VersionContext,
    fields,
)
from api.app.db.orm import ORMConnection, execute_orm, orm_all, orm_one
from api.app.schemas.users import UserRole
from sqlalchemy import delete, exists, func, insert, or_, select, update


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
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> UserRecord:
        row = await orm_one(
            self.connection,
            insert(User)
            .values(
                email=email, display_name=display_name, password_hash=password_hash, role="user"
            )
            .returning(*fields(User)),
        )
        if row is None:
            raise RuntimeError("user insert returned no row")
        return _user_from_row(row)

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await orm_one(self.connection, select(*fields(User)).where(User.email == email))
        return _user_from_row(row) if row else None

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        row = await orm_one(self.connection, select(*fields(User)).where(User.id == user_id))
        return _user_from_row(row) if row else None

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
        await execute_orm(
            self.connection,
            insert(AuthSession).values(
                id=session_id, user_id=user_id, issued_at=issued_at, expires_at=expires_at
            ),
        )

    async def is_session_active(self, session_id: UUID, user_id: UUID) -> bool:
        row = await orm_one(
            self.connection,
            select(
                exists()
                .where(
                    AuthSession.id == session_id,
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > func.clock_timestamp(),
                )
                .label("active")
            ),
        )
        return bool(row and row["active"])

    async def revoke_session(self, session_id: UUID, user_id: UUID) -> None:
        await execute_orm(
            self.connection,
            update(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=func.current_timestamp(), revocation_reason="logout"),
        )

    async def export_account(self, user_id: UUID) -> dict[str, list[dict[str, Any]]]:
        queries = {
            "owned_projects": select(
                Project.id,
                Project.name,
                Project.key,
                Project.description,
                Project.created_at,
                Project.updated_at,
            )
            .where(Project.owner_id == user_id)
            .order_by(Project.created_at, Project.id),
            "memberships": select(ProjectMember.project_id, ProjectMember.created_at)
            .where(ProjectMember.user_id == user_id)
            .order_by(ProjectMember.created_at, ProjectMember.project_id),
            "prompt_versions": select(
                VersionContext.id,
                VersionContext.prompt_id,
                VersionContext.version_number,
                VersionContext.parent_version_id,
                VersionContext.template_body,
                VersionContext.variables,
                VersionContext.model_config,
                VersionContext.commit_message,
                VersionContext.created_at,
            )
            .where(VersionContext.created_by == user_id)
            .order_by(VersionContext.created_at, VersionContext.id),
            "runs": select(
                RunContext.id,
                RunContext.project_id,
                RunContext.prompt_id,
                RunContext.version_id,
                RunContext.status,
                RunContext.provider,
                RunContext.model,
                RunContext.input_variables,
                RunContext.output_text,
                RunContext.prompt_tokens,
                RunContext.completion_tokens,
                RunContext.latency_ms,
                RunContext.cost,
                RunContext.error_code,
                RunContext.created_at,
            )
            .where(RunContext.user_id == user_id)
            .order_by(RunContext.created_at, RunContext.id),
            "deployments": select(
                DeploymentContext.id,
                DeploymentContext.prompt_id,
                DeploymentContext.version_id,
                DeploymentContext.environment,
                DeploymentContext.status,
                DeploymentContext.request_note,
                DeploymentContext.review_note,
                DeploymentContext.rollback_reason,
                DeploymentContext.rollback_of_id,
                DeploymentContext.requested_at,
                DeploymentContext.reviewed_at,
                DeploymentContext.activated_at,
            )
            .where(
                or_(
                    DeploymentContext.requested_by == user_id,
                    DeploymentContext.reviewed_by == user_id,
                )
            )
            .order_by(DeploymentContext.requested_at, DeploymentContext.id),
            "api_tokens": select(
                ApiToken.id,
                ApiToken.project_id,
                ApiToken.name,
                ApiToken.token_prefix,
                ApiToken.created_at,
                ApiToken.expires_at,
                ApiToken.revoked_at,
            )
            .where(ApiToken.created_by == user_id)
            .order_by(ApiToken.created_at, ApiToken.id),
        }
        return {name: await orm_all(self.connection, query) for name, query in queries.items()}

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
        await execute_orm(
            self.connection,
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None)
            ),
        )
        await execute_orm(
            self.connection,
            insert(PasswordResetToken).values(
                user_id=user_id, token_hash=token_hash, expires_at=expires_at
            ),
        )

    async def create_email_verification_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        await execute_orm(
            self.connection,
            insert(EmailVerificationToken).values(
                user_id=user_id, token_hash=token_hash, expires_at=expires_at
            ),
        )

    async def confirm_email_verification(self, token_hash: str) -> bool:
        cursor = await self.connection.execute(
            "SELECT confirm_email_verification(%s) AS confirmed",
            (token_hash,),
        )
        row = await cursor.fetchone()
        return bool(row and row["confirmed"])

    async def replace_email_verification_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        cooldown_seconds: int,
    ) -> int | None:
        locked = await orm_one(
            self.connection, select(User.id).where(User.id == user_id).with_for_update()
        )
        if locked is None:
            raise RuntimeError("verification user disappeared during replacement")
        latest_row = await orm_one(
            self.connection,
            select(EmailVerificationToken.created_at)
            .where(EmailVerificationToken.user_id == user_id)
            .order_by(EmailVerificationToken.created_at.desc(), EmailVerificationToken.id.desc())
            .limit(1),
        )
        if latest_row:
            remaining = (
                cast(datetime, latest_row["created_at"])
                + timedelta(seconds=cooldown_seconds)
                - datetime.now(UTC)
            ).total_seconds()
            if remaining > 0:
                return max(1, ceil(remaining))
        await execute_orm(
            self.connection,
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id, EmailVerificationToken.used_at.is_(None)
            )
            .values(used_at=func.clock_timestamp()),
        )
        await self.create_email_verification_token(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        return None

    async def lock_password_reset_user(self, token_hash: str) -> UserRecord | None:
        row = await orm_one(
            self.connection,
            select(*fields(User))
            .join(PasswordResetToken, PasswordResetToken.user_id == User.id)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > func.clock_timestamp(),
                User.is_active,
            )
            .with_for_update(of=User),
        )
        return _user_from_row(row) if row else None

    async def password_history(self, user_id: UUID) -> list[str]:
        rows = await orm_all(
            self.connection,
            select(PasswordHistory.password_hash).where(PasswordHistory.user_id == user_id),
        )
        return [str(row["password_hash"]) for row in rows]

    async def consume_password_reset_token(self, *, token_hash: str, password_hash: str) -> bool:
        cursor = await self.connection.execute(
            "SELECT consume_password_reset_token(%s, %s) AS consumed",
            (token_hash, password_hash),
        )
        row = await cursor.fetchone()
        return bool(row and row["consumed"])

    async def is_project_member(self, user_id: UUID, project_id: UUID) -> bool:
        row = await orm_one(
            self.connection,
            select(
                exists()
                .where(ProjectMember.user_id == user_id, ProjectMember.project_id == project_id)
                .label("allowed")
            ),
        )
        return bool(row and row["allowed"])

    async def is_project_owner(self, user_id: UUID, project_id: UUID) -> bool:
        row = await orm_one(
            self.connection,
            select(
                exists()
                .where(Project.owner_id == user_id, Project.id == project_id)
                .label("allowed")
            ),
        )
        return bool(row and row["allowed"])

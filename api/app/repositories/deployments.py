"""Scoped deployment lifecycle persistence."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from api.app.db.models import Deployment, DeploymentContext, ProjectMember, Prompt, PromptVersion
from api.app.db.orm import ORMConnection, orm_one
from api.app.repositories.pagination import read_page
from api.app.schemas.deployments import (
    DeploymentEnvironment,
    DeploymentResponse,
    DeploymentStatus,
    DeploymentTimelineEvent,
)
from api.app.security import UserRole
from sqlalchemy import literal, or_, select, update

_DEPLOYMENT_COLUMNS = """
    d.id, p.project_id, d.prompt_id, p.key AS prompt_key,
    d.version_id, pv.version_number, d.environment, d.status,
    d.request_note, d.review_note, d.rollback_reason, d.rollback_of_id,
    requester.id AS requester_id, requester.display_name AS requester_display_name,
    reviewer.id AS reviewer_id, reviewer.display_name AS reviewer_display_name,
    d.requested_at, d.reviewed_at, d.activated_at
"""


def _deployment_from_row(row: Mapping[str, Any]) -> DeploymentResponse:
    from api.app.schemas.deployments import DeploymentActorResponse

    reviewer = None
    if row["reviewer_id"] is not None:
        reviewer = DeploymentActorResponse(
            id=row["reviewer_id"], display_name=row["reviewer_display_name"]
        )
    return DeploymentResponse(
        id=row["id"],
        project_id=row["project_id"],
        prompt_id=row["prompt_id"],
        prompt_key=row["prompt_key"],
        version_id=row["version_id"],
        version_number=row["version_number"],
        environment=row["environment"],
        status=row["status"],
        request_note=row["request_note"],
        review_note=row["review_note"],
        rollback_reason=row["rollback_reason"],
        rollback_of_id=row["rollback_of_id"],
        requested_by=DeploymentActorResponse(
            id=row["requester_id"], display_name=row["requester_display_name"]
        ),
        reviewed_by=reviewer,
        requested_at=row["requested_at"],
        reviewed_at=row["reviewed_at"],
        activated_at=row["activated_at"],
    )


class DeploymentRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def set_audit_context(self, actor_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), set_config('app.request_id', %s, true)",
            (str(actor_id), request_id),
        )

    async def lock_version_access(self, version_id: UUID, user_id: UUID, role: UserRole) -> bool:
        statement = (
            select(PromptVersion.id)
            .join(Prompt, Prompt.id == PromptVersion.prompt_id)
            .where(PromptVersion.id == version_id)
        )
        if role == "admin":
            statement = statement.with_for_update(
                read=True, key_share=True, of=(PromptVersion, Prompt)
            )
        else:
            statement = (
                statement.join(ProjectMember, ProjectMember.project_id == Prompt.project_id)
                .where(ProjectMember.user_id == user_id)
                .with_for_update(
                    read=True, key_share=True, of=(PromptVersion, Prompt, ProjectMember)
                )
            )
        return await orm_one(self.connection, statement) is not None

    async def create(
        self,
        *,
        version_id: UUID,
        environment: DeploymentEnvironment,
        requested_by: UUID,
        request_note: str | None,
    ) -> DeploymentResponse:
        cursor = await self.connection.execute(
            """
            SELECT (request_deployment(
                p_version_id => %s,
                p_environment => %s,
                p_requested_by => %s,
                p_request_note => %s
            )).id AS id
            """,
            (version_id, environment, requested_by, request_note),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("deployment function returned no row")
        deployment = await self.get(row["id"])
        if deployment is None:
            raise RuntimeError("created deployment was not returned")
        return deployment

    async def get(self, deployment_id: UUID) -> DeploymentResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_DEPLOYMENT_COLUMNS}
            FROM deployment_context d
            JOIN prompts p ON p.id = d.prompt_id
            JOIN prompt_versions pv ON pv.id = d.version_id
            JOIN users requester ON requester.id = d.requested_by
            LEFT JOIN users reviewer ON reviewer.id = d.reviewed_by
            WHERE d.id = %s
            """,
            (deployment_id,),
        )
        row = await cursor.fetchone()
        return _deployment_from_row(row) if row else None

    async def get_scoped(
        self, deployment_id: UUID, user_id: UUID, role: UserRole
    ) -> DeploymentResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_DEPLOYMENT_COLUMNS}
            FROM deployment_context d
            JOIN prompts p ON p.id = d.prompt_id
            JOIN prompt_versions pv ON pv.id = d.version_id
            JOIN users requester ON requester.id = d.requested_by
            LEFT JOIN users reviewer ON reviewer.id = d.reviewed_by
            WHERE d.id = %s
              AND (%s = 'admin' OR EXISTS (
                  SELECT 1 FROM project_members pm
                  WHERE pm.project_id = p.project_id AND pm.user_id = %s
              ))
            """,
            (deployment_id, role, user_id),
        )
        row = await cursor.fetchone()
        return _deployment_from_row(row) if row else None

    async def list_scoped(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        project_id: UUID | None,
        prompt_id: UUID | None,
        environment: DeploymentEnvironment | None,
        status: DeploymentStatus | None,
        page: int,
        page_size: int,
        pending_admin_queue: bool = False,
    ) -> tuple[list[DeploymentResponse], int]:
        where: list[str] = []
        parameters: list[Any] = []
        if pending_admin_queue:
            where.extend(["d.environment = 'prod'", "d.status = 'pending'"])
        else:
            where.append(
                "(%s = 'admin' OR EXISTS (SELECT 1 FROM project_members pm "
                "WHERE pm.project_id = p.project_id AND pm.user_id = %s))"
            )
            parameters.extend([role, user_id])
        for clause, value in (
            ("p.project_id = %s", project_id),
            ("d.prompt_id = %s", prompt_id),
            ("d.environment = %s", environment),
            ("d.status = %s", status),
        ):
            if value is not None:
                where.append(clause)
                parameters.append(value)
        where_sql = " AND ".join(where)
        rows, total = await read_page(
            self.connection,
            count_query=f"""SELECT count(*) AS total FROM deployment_context d
                JOIN prompts p ON p.id = d.prompt_id WHERE {where_sql}""",
            items_query=f"""
            SELECT {_DEPLOYMENT_COLUMNS}
            FROM deployment_context d
            JOIN prompts p ON p.id = d.prompt_id
            JOIN prompt_versions pv ON pv.id = d.version_id
            JOIN users requester ON requester.id = d.requested_by
            LEFT JOIN users reviewer ON reviewer.id = d.reviewed_by
            WHERE {where_sql}
            ORDER BY d.requested_at DESC, d.id DESC
            LIMIT %s OFFSET %s
            """,
            parameters=parameters,
            page=page,
            page_size=page_size,
            order_by="requested_at DESC, id DESC",
        )
        return [_deployment_from_row(row) for row in rows], total

    async def timeline(
        self, prompt_id: UUID, environment: DeploymentEnvironment
    ) -> list[DeploymentTimelineEvent]:
        cursor = await self.connection.execute(
            """
            SELECT d.id, d.version_id, pv.version_number, d.status,
                   d.requested_at, d.reviewed_at, d.activated_at
            FROM deployment_context d
            JOIN prompt_versions pv ON pv.id = d.version_id
            WHERE d.prompt_id = %s AND d.environment = %s
            ORDER BY d.requested_at DESC, d.id DESC
            LIMIT 100
            """,
            (prompt_id, environment),
        )
        return [DeploymentTimelineEvent.model_validate(row) for row in await cursor.fetchall()]

    async def cancel(
        self, deployment_id: UUID, actor_id: UUID, role: UserRole
    ) -> DeploymentResponse | None:
        row = await orm_one(
            self.connection,
            update(Deployment)
            .where(
                Deployment.id == deployment_id,
                Deployment.status == "pending",
                or_(Deployment.requested_by == actor_id, literal(role == "admin")),
            )
            .values(status="cancelled")
            .returning(Deployment.id),
        )
        return await self.get(row["id"]) if row else None

    async def review(
        self,
        deployment_id: UUID,
        admin_id: UUID,
        *,
        approve: bool,
        review_note: str | None,
    ) -> DeploymentResponse:
        cursor = await self.connection.execute(
            """
            SELECT (review_production_deployment(
                p_deployment_id => %s, p_admin_id => %s,
                p_approve => %s, p_review_note => %s
            )).id AS id
            """,
            (deployment_id, admin_id, approve, review_note),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("review function returned no row")
        deployment = await self.get(row["id"])
        if deployment is None:
            raise RuntimeError("reviewed deployment was not returned")
        return deployment

    async def rollback(
        self, prompt_id: UUID, version_id: UUID, admin_id: UUID, reason: str
    ) -> DeploymentResponse:
        cursor = await self.connection.execute(
            """
            SELECT (rollback_deployment(
                p_prompt_id => %s, p_target_version_id => %s,
                p_admin_id => %s, p_reason => %s, p_environment => 'prod'
            )).id AS id
            """,
            (prompt_id, version_id, admin_id, reason),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("rollback function returned no row")
        deployment = await self.get(row["id"])
        if deployment is None:
            raise RuntimeError("rollback deployment was not returned")
        return deployment

    async def active_version_id(
        self, prompt_id: UUID, environment: DeploymentEnvironment
    ) -> UUID | None:
        row = await orm_one(
            self.connection,
            select(DeploymentContext.version_id).where(
                DeploymentContext.prompt_id == prompt_id,
                DeploymentContext.environment == environment,
                DeploymentContext.status == "active",
            ),
        )
        return row["version_id"] if row else None

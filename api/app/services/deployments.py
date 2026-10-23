"""Deployment request, history, cancellation, and review use cases."""

from uuid import UUID

from api.app.errors import AppError
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.users import UserRecord
from api.app.repositories.versions import VersionRepository
from api.app.schemas.common import Page
from api.app.schemas.deployments import (
    DeploymentCreate,
    DeploymentDetailResponse,
    DeploymentEnvironment,
    DeploymentResponse,
    DeploymentReviewDetailResponse,
    DeploymentStatus,
)
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    NoDataFound,
    SerializationFailure,
)


class DeploymentService:
    def __init__(
        self,
        deployments: DeploymentRepository,
        versions: VersionRepository,
        runs: RunRepository,
        request_id: str,
    ) -> None:
        self.deployments = deployments
        self.versions = versions
        self.runs = runs
        self.request_id = request_id

    async def create(self, payload: DeploymentCreate, actor: UserRecord) -> DeploymentResponse:
        if not await self.deployments.lock_version_access(payload.version_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Prompt version was not found")
        await self.deployments.set_audit_context(actor.id, self.request_id)
        try:
            return await self.deployments.create(
                version_id=payload.version_id,
                environment=payload.environment,
                requested_by=actor.id,
                request_note=payload.request_note,
            )
        except (ForeignKeyViolation, NoDataFound) as exc:
            raise AppError(404, "not_found", "Prompt version was not found") from exc

    async def list(
        self,
        actor: UserRecord,
        *,
        project_id: UUID | None,
        prompt_id: UUID | None,
        environment: DeploymentEnvironment | None,
        status: DeploymentStatus | None,
        page: int,
        page_size: int,
    ) -> Page[DeploymentResponse]:
        items, total = await self.deployments.list_scoped(
            user_id=actor.id,
            role=actor.role,
            project_id=project_id,
            prompt_id=prompt_id,
            environment=environment,
            status=status,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def detail(self, deployment_id: UUID, actor: UserRecord) -> DeploymentDetailResponse:
        deployment = await self.deployments.get_scoped(deployment_id, actor.id, actor.role)
        if deployment is None:
            raise AppError(404, "not_found", "Deployment was not found")
        timeline = await self.deployments.timeline(deployment.prompt_id, deployment.environment)
        return DeploymentDetailResponse(**deployment.model_dump(), timeline=timeline)

    async def cancel(self, deployment_id: UUID, actor: UserRecord) -> DeploymentResponse:
        deployment = await self.deployments.get_scoped(deployment_id, actor.id, actor.role)
        if deployment is None:
            raise AppError(404, "not_found", "Deployment was not found")
        if actor.role != "admin" and deployment.requested_by.id != actor.id:
            raise AppError(403, "forbidden", "Only the requester can cancel this deployment")
        if deployment.status != "pending":
            raise AppError(409, "invalid_state", "Only pending deployments can be cancelled")
        await self.deployments.set_audit_context(actor.id, self.request_id)
        cancelled = await self.deployments.cancel(deployment_id, actor.id, actor.role)
        if cancelled is None:
            raise AppError(409, "invalid_state", "Deployment is no longer pending")
        return cancelled

    async def pending(
        self,
        *,
        project_id: UUID | None,
        prompt_id: UUID | None,
        page: int,
        page_size: int,
    ) -> Page[DeploymentResponse]:
        items, total = await self.deployments.list_scoped(
            user_id=UUID(int=0),
            role="admin",
            project_id=project_id,
            prompt_id=prompt_id,
            environment=None,
            status=None,
            page=page,
            page_size=page_size,
            pending_admin_queue=True,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def review_detail(self, deployment_id: UUID) -> DeploymentReviewDetailResponse:
        deployment = await self.deployments.get(deployment_id)
        if deployment is None:
            raise AppError(404, "not_found", "Deployment was not found")
        requested = await self.versions.get(deployment.version_id)
        if requested is None:
            raise AppError(404, "not_found", "Prompt version was not found")
        active_id = await self.deployments.active_version_id(deployment.prompt_id, "prod")
        active = await self.versions.get(active_id) if active_id else None
        recent_runs, _ = await self.runs.list_scoped(
            user_id=UUID(int=0),
            role="admin",
            project_id=deployment.project_id,
            prompt_id=deployment.prompt_id,
            version_id=deployment.version_id,
            status=None,
            model=None,
            search=None,
            created_from=None,
            created_to=None,
            page=1,
            page_size=5,
        )
        return DeploymentReviewDetailResponse(
            deployment=deployment,
            requested_version=requested,
            active_version=active,
            recent_runs=recent_runs,
        )

    async def review(
        self,
        deployment_id: UUID,
        actor: UserRecord,
        *,
        approve: bool,
        review_note: str | None,
    ) -> DeploymentResponse:
        await self.deployments.set_audit_context(actor.id, self.request_id)
        try:
            return await self.deployments.review(
                deployment_id,
                actor.id,
                approve=approve,
                review_note=review_note,
            )
        except SerializationFailure as exc:
            raise AppError(409, "already_reviewed", "Deployment was already reviewed") from exc
        except CheckViolation as exc:
            raise AppError(422, "validation_error", "Review note is required") from exc
        except NoDataFound as exc:
            message = str(exc)
            if "deployment_not_found" in message:
                raise AppError(404, "not_found", "Deployment was not found") from exc
            if "already_reviewed" in message:
                raise AppError(409, "already_reviewed", "Deployment was already reviewed") from exc
            raise

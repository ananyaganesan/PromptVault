"""Auditable production rollback use case."""

from uuid import UUID

from api.app.errors import AppError
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.users import UserRecord
from api.app.schemas.deployments import DeploymentResponse, RollbackCreate
from psycopg.errors import CheckViolation, NoDataFound


class RollbackService:
    def __init__(self, deployments: DeploymentRepository, request_id: str) -> None:
        self.deployments = deployments
        self.request_id = request_id

    async def rollback(
        self, prompt_id: UUID, payload: RollbackCreate, actor: UserRecord
    ) -> DeploymentResponse:
        await self.deployments.set_audit_context(actor.id, self.request_id)
        try:
            return await self.deployments.rollback(
                prompt_id, payload.target_version_id, actor.id, payload.reason
            )
        except CheckViolation as exc:
            raise AppError(
                409, "invalid_rollback_target", "Rollback target must be an earlier version"
            ) from exc
        except NoDataFound as exc:
            message = str(exc)
            if "version_not_found" in message:
                raise AppError(404, "not_found", "Prompt or target version was not found") from exc
            if "no_active_deployment" in message:
                raise AppError(
                    409, "no_active_deployment", "Prompt has no active production deployment"
                ) from exc
            raise

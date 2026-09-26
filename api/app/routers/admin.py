"""Phase 4 Super Admin deployment review and rollback endpoints."""

from typing import Annotated
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.authorization import SuperAdmin
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import error_responses
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.versions import VersionRepository
from api.app.schemas.common import Page
from api.app.schemas.deployments import (
    DeploymentReject,
    DeploymentResponse,
    DeploymentReview,
    DeploymentReviewDetailResponse,
    RollbackCreate,
)
from api.app.services.deployments import DeploymentService
from api.app.services.rollback import RollbackService
from fastapi import APIRouter, Depends, Query, Request, status

router = APIRouter(prefix="/api/v1/admin", tags=["admin deployments"])


def get_admin_deployment_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> DeploymentService:
    return DeploymentService(
        DeploymentRepository(connection),
        VersionRepository(connection),
        RunRepository(connection),
        get_request_id(request),
    )


def get_rollback_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> RollbackService:
    return RollbackService(DeploymentRepository(connection), get_request_id(request))


AdminDeploymentService = Annotated[
    DeploymentService, Depends(get_admin_deployment_service)
]
AdminRollbackService = Annotated[RollbackService, Depends(get_rollback_service)]


@router.get(
    "/deployments/pending",
    response_model=Page[DeploymentResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(allow_query_parameters("project_id", "prompt_id", "page", "page_size"))
    ],
)
async def pending_deployments(
    _admin: SuperAdmin,
    service: AdminDeploymentService,
    project_id: UUID | None = None,
    prompt_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[DeploymentResponse]:
    return await service.pending(
        project_id=project_id, prompt_id=prompt_id, page=page, page_size=page_size
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentReviewDetailResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def deployment_review_detail(
    deployment_id: UUID,
    _admin: SuperAdmin,
    service: AdminDeploymentService,
) -> DeploymentReviewDetailResponse:
    return await service.review_detail(deployment_id)


@router.post(
    "/deployments/{deployment_id}/approve",
    response_model=DeploymentResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def approve_deployment(
    deployment_id: UUID,
    payload: DeploymentReview,
    admin: SuperAdmin,
    service: AdminDeploymentService,
) -> DeploymentResponse:
    return await service.review(
        deployment_id, admin, approve=True, review_note=payload.review_note
    )


@router.post(
    "/deployments/{deployment_id}/reject",
    response_model=DeploymentResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def reject_deployment(
    deployment_id: UUID,
    payload: DeploymentReject,
    admin: SuperAdmin,
    service: AdminDeploymentService,
) -> DeploymentResponse:
    return await service.review(
        deployment_id, admin, approve=False, review_note=payload.review_note
    )


@router.post(
    "/prompts/{prompt_id}/rollback",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def rollback_prompt(
    prompt_id: UUID,
    payload: RollbackCreate,
    admin: SuperAdmin,
    service: AdminRollbackService,
) -> DeploymentResponse:
    return await service.rollback(prompt_id, payload, admin)

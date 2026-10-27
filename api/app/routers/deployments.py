"""Member-scoped deployment lifecycle endpoints."""

from typing import Annotated
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import error_responses
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.versions import VersionRepository
from api.app.schemas.common import Page
from api.app.schemas.deployments import (
    DeploymentCreate,
    DeploymentDetailResponse,
    DeploymentEnvironment,
    DeploymentResponse,
    DeploymentStatus,
)
from api.app.schemas.release_validation import ReleaseValidationLink
from api.app.services.deployments import DeploymentService
from fastapi import APIRouter, Depends, Query, Request, status

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


def get_deployment_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> DeploymentService:
    return DeploymentService(
        DeploymentRepository(connection),
        VersionRepository(connection),
        RunRepository(connection),
        get_request_id(request),
    )


DeploymentServiceDependency = Annotated[DeploymentService, Depends(get_deployment_service)]


@router.post(
    "",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_deployment(
    payload: DeploymentCreate,
    current_user: CurrentUser,
    service: DeploymentServiceDependency,
) -> DeploymentResponse:
    return await service.create(payload, current_user)


@router.get(
    "",
    response_model=Page[DeploymentResponse],
    responses=error_responses(400, 401, 422),
    dependencies=[
        Depends(
            allow_query_parameters(
                "project_id", "prompt_id", "environment", "status", "page", "page_size"
            )
        )
    ],
)
async def list_deployments(
    current_user: CurrentUser,
    service: DeploymentServiceDependency,
    project_id: UUID | None = None,
    prompt_id: UUID | None = None,
    environment: DeploymentEnvironment | None = None,
    status_filter: Annotated[DeploymentStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[DeploymentResponse]:
    return await service.list(
        current_user,
        project_id=project_id,
        prompt_id=prompt_id,
        environment=environment,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{deployment_id}",
    response_model=DeploymentDetailResponse,
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_deployment(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: DeploymentServiceDependency,
) -> DeploymentDetailResponse:
    return await service.detail(deployment_id, current_user)


@router.post(
    "/{deployment_id}/cancel",
    response_model=DeploymentResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def cancel_deployment(
    deployment_id: UUID,
    current_user: CurrentUser,
    service: DeploymentServiceDependency,
) -> DeploymentResponse:
    return await service.cancel(deployment_id, current_user)


@router.post(
    "/{deployment_id}/validation",
    response_model=DeploymentResponse,
    responses=error_responses(401, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def replace_validation(
    deployment_id: UUID,
    payload: ReleaseValidationLink,
    current_user: CurrentUser,
    service: DeploymentServiceDependency,
) -> DeploymentResponse:
    return await service.revalidate(deployment_id, payload.validation_id, current_user)

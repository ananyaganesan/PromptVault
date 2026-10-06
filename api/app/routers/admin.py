"""Super Admin deployment review and governance endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.authorization import SuperAdmin
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import error_responses
from api.app.repositories.admin import AdminRepository
from api.app.repositories.audit import AuditRepository
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.versions import VersionRepository
from api.app.schemas.admin import (
    AdminDashboardResponse,
    AdminUserResponse,
    AdminUserUpdate,
    AuditEventResponse,
    MaintenanceStatusResponse,
    ModelPricingCreate,
    ModelPricingResponse,
    PartitionCreateResponse,
    ProviderKeyCreate,
    ProviderKeyResponse,
    ViewRefreshResponse,
)
from api.app.schemas.budgets import BudgetCreate, BudgetResponse, BudgetUpdate
from api.app.schemas.common import Page
from api.app.schemas.deployments import (
    DeploymentReject,
    DeploymentResponse,
    DeploymentReview,
    DeploymentReviewDetailResponse,
    RollbackCreate,
)
from api.app.schemas.runs import RunResponse, RunStatus
from api.app.schemas.users import UserRole
from api.app.services.admin import AdminGovernanceService
from api.app.services.audit import AuditService
from api.app.services.deployments import DeploymentService
from api.app.services.rollback import RollbackService
from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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


def get_admin_governance_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> AdminGovernanceService:
    return AdminGovernanceService(
        AdminRepository(connection),
        get_request_id(request),
        request.app.state.settings.resolved_provider_encryption_key,
    )


def get_audit_service(
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> AuditService:
    return AuditService(AuditRepository(connection))


AdminGovernance = Annotated[AdminGovernanceService, Depends(get_admin_governance_service)]
AdminAudit = Annotated[AuditService, Depends(get_audit_service)]


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


@router.get(
    "/dashboard",
    response_model=AdminDashboardResponse,
    responses=error_responses(400, 401, 403, 422),
    dependencies=[Depends(allow_query_parameters("month"))],
)
async def admin_dashboard(
    _admin: SuperAdmin,
    service: AdminGovernance,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> AdminDashboardResponse:
    return await service.dashboard(month)


@router.get(
    "/users",
    response_model=Page[AdminUserResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(
            allow_query_parameters("search", "role", "is_active", "page", "page_size")
        )
    ],
)
async def list_admin_users(
    _admin: SuperAdmin,
    service: AdminGovernance,
    search: Annotated[str | None, Query(max_length=320)] = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AdminUserResponse]:
    return await service.list_users(
        search=search,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def update_admin_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> AdminUserResponse:
    return await service.update_user(user_id, payload, admin)


@router.get(
    "/budgets",
    response_model=Page[BudgetResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[Depends(allow_query_parameters("user_id", "project_id", "page", "page_size"))],
)
async def list_admin_budgets(
    _admin: SuperAdmin,
    service: AdminGovernance,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[BudgetResponse]:
    return await service.list_budgets(
        user_id=user_id, project_id=project_id, page=page, page_size=page_size
    )


@router.post(
    "/budgets",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_admin_budget(
    payload: BudgetCreate,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> BudgetResponse:
    return await service.create_budget(payload, admin)


@router.patch(
    "/budgets/{budget_id}",
    response_model=BudgetResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def update_admin_budget(
    budget_id: UUID,
    payload: BudgetUpdate,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> BudgetResponse:
    return await service.update_budget(budget_id, payload, admin)


@router.delete(
    "/budgets/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def delete_admin_budget(
    budget_id: UUID,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> Response:
    await service.delete_budget(budget_id, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/provider-keys",
    response_model=Page[ProviderKeyResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[Depends(allow_query_parameters("provider", "page", "page_size"))],
)
async def list_admin_provider_keys(
    _admin: SuperAdmin,
    service: AdminGovernance,
    provider: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ProviderKeyResponse]:
    return await service.list_provider_keys(
        provider=provider, page=page, page_size=page_size
    )


@router.post(
    "/provider-keys",
    response_model=ProviderKeyResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_admin_provider_key(
    payload: ProviderKeyCreate,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> ProviderKeyResponse:
    return await service.create_provider_key(payload, admin)


@router.delete(
    "/provider-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def deactivate_admin_provider_key(
    key_id: UUID,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> Response:
    await service.deactivate_provider_key(key_id, admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/model-pricing",
    response_model=Page[ModelPricingResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(allow_query_parameters("provider", "model", "page", "page_size"))
    ],
)
async def list_admin_model_pricing(
    _admin: SuperAdmin,
    service: AdminGovernance,
    provider: Annotated[str | None, Query(max_length=80)] = None,
    model: Annotated[str | None, Query(max_length=160)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ModelPricingResponse]:
    return await service.list_pricing(
        provider=provider, model=model, page=page, page_size=page_size
    )


@router.post(
    "/model-pricing",
    response_model=ModelPricingResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_admin_model_pricing(
    payload: ModelPricingCreate,
    admin: SuperAdmin,
    service: AdminGovernance,
) -> ModelPricingResponse:
    return await service.create_pricing(payload, admin)


@router.get(
    "/runs",
    response_model=Page[RunResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(
            allow_query_parameters(
                "search", "user_id", "project_id", "prompt_id", "model", "status",
                "from", "to", "page", "page_size"
            )
        )
    ],
)
async def list_admin_runs(
    _admin: SuperAdmin,
    service: AdminGovernance,
    search: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    prompt_id: UUID | None = None,
    model: Annotated[str | None, Query(max_length=160)] = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[RunResponse]:
    return await service.list_runs(
        search=search,
        user_id=user_id,
        project_id=project_id,
        prompt_id=prompt_id,
        model=model,
        status=status_filter,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/audit",
    response_model=Page[AuditEventResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(
            allow_query_parameters(
                "actor_id", "action", "entity_type", "entity_id",
                "from", "to", "page", "page_size"
            )
        )
    ],
)
async def list_admin_audit(
    _admin: SuperAdmin,
    service: AdminAudit,
    actor_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=120)] = None,
    entity_type: Annotated[str | None, Query(max_length=80)] = None,
    entity_id: UUID | None = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AuditEventResponse]:
    return await service.list_events(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/maintenance",
    response_model=MaintenanceStatusResponse,
    responses=error_responses(401, 403),
    dependencies=[Depends(allow_query_parameters())],
)
async def admin_maintenance_status(
    _admin: SuperAdmin,
    service: AdminGovernance,
) -> MaintenanceStatusResponse:
    return await service.maintenance_status()


@router.post(
    "/maintenance/refresh-views",
    response_model=ViewRefreshResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(401, 403),
    dependencies=[Depends(allow_query_parameters())],
)
async def refresh_admin_views(
    admin: SuperAdmin,
    service: AdminGovernance,
) -> ViewRefreshResponse:
    return await service.refresh_views(admin)


@router.post(
    "/maintenance/create-next-partition",
    response_model=PartitionCreateResponse,
    responses=error_responses(401, 403),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_admin_next_partition(
    admin: SuperAdmin,
    service: AdminGovernance,
) -> PartitionCreateResponse:
    return await service.create_next_partition(admin)

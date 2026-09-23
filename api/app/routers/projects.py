"""Project and membership endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.authorization import ProjectMember, ProjectOwner
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import error_responses
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.users import UserRepository
from api.app.schemas.common import Page
from api.app.schemas.projects import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from api.app.services.projects import ProjectService
from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1", tags=["projects"])


def get_project_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> ProjectService:
    return ProjectService(
        ProjectRepository(connection),
        UserRepository(connection),
        get_request_id(request),
    )


ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]


@router.get(
    "/projects",
    response_model=Page[ProjectResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[
        Depends(allow_query_parameters("search", "page", "page_size", "sort", "direction"))
    ],
)
async def list_projects(
    current_user: CurrentUser,
    service: ProjectServiceDependency,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sort: Literal["name", "created_at", "updated_at"] = "updated_at",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[ProjectResponse]:
    return await service.list(
        current_user,
        search=search,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    return await service.create(payload, current_user)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_project(
    project_id: UUID,
    current_user: ProjectMember,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    return await service.require_member_project(project_id, current_user)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: ProjectOwner,
    service: ProjectServiceDependency,
) -> ProjectResponse:
    return await service.update(project_id, payload, current_user)


@router.get(
    "/projects/{project_id}/members",
    response_model=Page[ProjectMemberResponse],
    responses=error_responses(400, 401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters("page", "page_size"))],
)
async def list_project_members(
    project_id: UUID,
    current_user: ProjectMember,
    service: ProjectServiceDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ProjectMemberResponse]:
    return await service.list_members(
        project_id, current_user, page=page, page_size=page_size
    )


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def add_project_member(
    project_id: UUID,
    payload: ProjectMemberCreate,
    current_user: ProjectOwner,
    service: ProjectServiceDependency,
) -> ProjectMemberResponse:
    return await service.add_member(project_id, str(payload.email), current_user)


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    current_user: ProjectOwner,
    service: ProjectServiceDependency,
) -> Response:
    await service.remove_member(project_id, user_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

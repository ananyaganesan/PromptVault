"""Immutable prompt-version endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.prompt_versioning import PromptService
from api.app.dependencies.query import allow_query_parameters
from api.app.errors import error_responses
from api.app.schemas.common import Page
from api.app.schemas.versions import (
    PromptVersionCreate,
    PromptVersionResponse,
    VersionDiffResponse,
    VersionLineageResponse,
)
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1", tags=["versions"])


@router.post(
    "/prompts/{prompt_id}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_version(
    prompt_id: UUID,
    payload: PromptVersionCreate,
    current_user: CurrentUser,
    service: PromptService,
) -> PromptVersionResponse:
    return await service.create_version(prompt_id, payload, current_user)


@router.get(
    "/prompts/{prompt_id}/versions",
    response_model=Page[PromptVersionResponse],
    responses=error_responses(400, 401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters("page", "page_size", "sort", "direction"))],
)
async def list_versions(
    prompt_id: UUID,
    current_user: CurrentUser,
    service: PromptService,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sort: Literal["version_number", "created_at"] = "version_number",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[PromptVersionResponse]:
    return await service.list_versions(
        prompt_id,
        current_user,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )


@router.get(
    "/versions/{version_id}",
    response_model=PromptVersionResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_version(
    version_id: UUID,
    current_user: CurrentUser,
    service: PromptService,
) -> PromptVersionResponse:
    return await service.require_version(version_id, current_user)


@router.get(
    "/versions/{version_id}/diff",
    response_model=VersionDiffResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters("against"))],
)
async def diff_versions(
    version_id: UUID,
    against: UUID,
    current_user: CurrentUser,
    service: PromptService,
) -> VersionDiffResponse:
    return await service.diff(version_id, against, current_user)


@router.get(
    "/versions/{version_id}/lineage",
    response_model=VersionLineageResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_version_lineage(
    version_id: UUID,
    current_user: CurrentUser,
    service: PromptService,
) -> VersionLineageResponse:
    return await service.lineage(version_id, current_user)

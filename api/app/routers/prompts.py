"""Prompt metadata endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.authorization import ProjectMember
from api.app.dependencies.prompt_versioning import PromptService
from api.app.dependencies.query import allow_query_parameters
from api.app.errors import error_responses
from api.app.schemas.common import Page
from api.app.schemas.prompts import (
    PromptCreate,
    PromptResponse,
    PromptSummaryResponse,
    PromptUpdate,
)
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1", tags=["prompts"])


@router.get(
    "/projects/{project_id}/prompts",
    response_model=Page[PromptSummaryResponse],
    responses=error_responses(400, 401, 403, 404, 422),
    dependencies=[
        Depends(allow_query_parameters("search", "page", "page_size", "sort", "direction"))
    ],
)
async def list_prompts(
    project_id: UUID,
    current_user: ProjectMember,
    service: PromptService,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sort: Literal["key", "name", "updated_at"] = "updated_at",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[PromptSummaryResponse]:
    return await service.list_prompts(
        project_id,
        current_user,
        search=search,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )


@router.post(
    "/projects/{project_id}/prompts",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_prompt(
    project_id: UUID,
    payload: PromptCreate,
    current_user: ProjectMember,
    service: PromptService,
) -> PromptResponse:
    return await service.create_prompt(project_id, payload, current_user)


@router.get(
    "/prompts/{prompt_id}",
    response_model=PromptResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_prompt(
    prompt_id: UUID,
    current_user: CurrentUser,
    service: PromptService,
) -> PromptResponse:
    return await service.get_prompt(prompt_id, current_user)


@router.patch(
    "/prompts/{prompt_id}",
    response_model=PromptResponse,
    responses=error_responses(401, 403, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def update_prompt(
    prompt_id: UUID,
    payload: PromptUpdate,
    current_user: CurrentUser,
    service: PromptService,
) -> PromptResponse:
    return await service.update_prompt(prompt_id, payload, current_user)

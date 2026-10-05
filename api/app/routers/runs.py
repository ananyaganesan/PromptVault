"""Run execution and scoped ledger endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from api.app.dependencies.auth import CurrentUser, DetachedCurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.runs import RunExecution, RunQuery
from api.app.errors import error_responses
from api.app.schemas.common import Page
from api.app.schemas.runs import RunCreate, RunResponse, RunStatus
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 409, 422, 502, 504),
    dependencies=[Depends(allow_query_parameters())],
)
async def execute_run(
    payload: RunCreate,
    current_user: DetachedCurrentUser,
    service: RunExecution,
) -> RunResponse:
    return await service.execute(payload, current_user)


@router.get(
    "",
    response_model=Page[RunResponse],
    responses=error_responses(400, 401, 422),
    dependencies=[
        Depends(
            allow_query_parameters(
                "project_id",
                "prompt_id",
                "version_id",
                "status",
                "model",
                "search",
                "from",
                "to",
                "page",
                "page_size",
            )
        )
    ],
)
async def list_runs(
    current_user: CurrentUser,
    service: RunQuery,
    project_id: UUID | None = None,
    prompt_id: UUID | None = None,
    version_id: UUID | None = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    model: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[RunResponse]:
    return await service.list_runs(
        current_user,
        project_id=project_id,
        prompt_id=prompt_id,
        version_id=version_id,
        status=status_filter,
        model=model,
        search=search,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    responses=error_responses(401, 404, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def get_run(
    run_id: UUID,
    current_user: CurrentUser,
    service: RunQuery,
) -> RunResponse:
    return await service.get(run_id, current_user)

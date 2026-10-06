"""Personal dashboard endpoints."""

from typing import Annotated

from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.runs import DashboardService
from api.app.errors import error_responses
from api.app.schemas.runs import PersonalDashboardResponse
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get(
    "/me",
    response_model=PersonalDashboardResponse,
    responses=error_responses(400, 401, 422),
    dependencies=[Depends(allow_query_parameters("month"))],
)
async def personal_dashboard(
    current_user: CurrentUser,
    service: DashboardService,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> PersonalDashboardResponse:
    return await service.personal_dashboard(current_user, month)

"""Run execution and dashboard service wiring."""

from typing import Annotated

from api.app.db.pool import PoolProtocol, get_pool
from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.request_context import get_request_id
from api.app.repositories.budgets import BudgetRepository
from api.app.repositories.runs import RunRepository
from api.app.services.analytics import AnalyticsService
from api.app.services.playground import RunExecutionService, RunQueryService
from fastapi import Depends, Request


def get_run_execution_service(
    request: Request,
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> RunExecutionService:
    return RunExecutionService(
        pool,
        get_request_id(request),
        request.app.state.settings.provider_timeout_seconds,
        request.app.state.settings.resolved_provider_encryption_key,
        request.app.state.settings.gemini_api_base_url,
    )


def get_run_query_service(
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> RunQueryService:
    return RunQueryService(RunRepository(connection))


def get_analytics_service(
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> AnalyticsService:
    return AnalyticsService(RunRepository(connection), BudgetRepository(connection))


RunExecution = Annotated[RunExecutionService, Depends(get_run_execution_service)]
RunQuery = Annotated[RunQueryService, Depends(get_run_query_service)]
DashboardService = Annotated[AnalyticsService, Depends(get_analytics_service)]

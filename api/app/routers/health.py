"""Operational liveness and readiness endpoints."""

from typing import Annotated

from api.app.db.health import check_database
from api.app.db.pool import PoolProtocol, get_pool
from api.app.errors import AppError, ErrorEnvelope
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(HealthResponse):
    database: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ErrorEnvelope, "description": "Database is unavailable"}},
)
async def readiness(
    request: Request,
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> ReadinessResponse:
    try:
        await check_database(
            pool,
            timeout_seconds=request.app.state.settings.database_health_timeout_seconds,
        )
    except Exception as exc:
        raise AppError(503, "not_ready", "Database readiness check failed") from exc
    return ReadinessResponse(status="ready", database="ok")

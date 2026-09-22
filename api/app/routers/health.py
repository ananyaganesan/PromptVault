"""Operational liveness and readiness endpoints."""

from typing import Annotated

from api.app.db.health import check_database
from api.app.db.pool import PoolProtocol, get_pool
from api.app.errors import AppError
from fastapi import APIRouter, Depends, Request

router = APIRouter(tags=["operations"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    request: Request,
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> dict[str, str]:
    try:
        await check_database(
            pool,
            timeout_seconds=request.app.state.settings.database_health_timeout_seconds,
        )
    except Exception as exc:
        raise AppError(503, "not_ready", "Database readiness check failed") from exc
    return {"status": "ready", "database": "ok"}

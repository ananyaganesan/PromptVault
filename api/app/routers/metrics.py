"""Internal Prometheus scrape endpoint."""

from typing import cast

from api.app.metrics import ApplicationMetrics
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["operations"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    application_metrics = cast(ApplicationMetrics, request.app.state.metrics)
    return Response(
        application_metrics.render(),
        media_type="text/plain; version=0.0.4",
    )

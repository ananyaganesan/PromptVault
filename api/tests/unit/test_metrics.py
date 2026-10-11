"""Safe Prometheus metrics surface."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from api.app.errors import AppError
from api.app.main import create_app
from fastapi.testclient import TestClient


class NoopPool:
    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[object]:
        yield object()


def test_metrics_report_requests_without_paths_or_query_values(test_settings) -> None:
    app = create_app(test_settings, pool_factory=lambda _: NoopPool())

    @app.get("/_test/error")
    async def test_error() -> None:
        raise AppError(401, "unauthorized", "Authentication is required")

    with TestClient(app) as client:
        assert client.get("/health?secret=not-a-label").status_code == 200
        assert client.get("/_test/error").status_code == 401
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'promptvault_http_requests_total{method="GET",status="200"} 1' in response.text
    assert "promptvault_http_request_duration_seconds_sum" in response.text
    assert "promptvault_process_uptime_seconds" in response.text
    assert 'promptvault_errors_total{code="unauthorized"} 1' in response.text
    assert "/health" not in response.text
    assert "not-a-label" not in response.text

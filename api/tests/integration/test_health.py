import asyncio
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from types import TracebackType

import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient


class FakeConnection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    async def execute(self, query: str) -> None:
        self.pool.executed.append(query)
        if self.pool.delay_seconds:
            await asyncio.sleep(self.pool.delay_seconds)
        if self.pool.error:
            raise self.pool.error


class FakeConnectionContext(AbstractAsyncContextManager[FakeConnection]):
    def __init__(self, pool: "FakePool") -> None:
        self.connection = FakeConnection(pool)

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakePool:
    def __init__(self, *, error: Exception | None = None, delay_seconds: float = 0) -> None:
        self.error = error
        self.delay_seconds = delay_seconds
        self.connection_count = 0
        self.executed: list[str] = []

    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None

    def connection(self) -> FakeConnectionContext:
        self.connection_count += 1
        return FakeConnectionContext(self)


@pytest.fixture
def fake_pool() -> FakePool:
    return FakePool()


@pytest.fixture
def app_client(test_settings: Settings, fake_pool: FakePool) -> Iterator[TestClient]:
    app = create_app(test_settings, pool_factory=lambda _: fake_pool)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def unready_client(test_settings: Settings) -> Iterator[TestClient]:
    pool = FakePool(error=ConnectionError("connection refused with private details"))
    app = create_app(test_settings, pool_factory=lambda _: pool)
    with TestClient(app) as client:
        yield client


def test_health_does_not_query_database(app_client: TestClient, fake_pool: FakePool) -> None:
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_pool.connection_count == 0


def test_ready_queries_database(app_client: TestClient, fake_pool: FakePool) -> None:
    response = app_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert fake_pool.executed == ["SELECT 1"]


def test_database_outage_only_breaks_readiness(unready_client: TestClient) -> None:
    ready = unready_client.get("/ready")
    live = unready_client.get("/health")

    assert ready.status_code == 503
    assert ready.json()["code"] == "not_ready"
    assert "connection refused" not in ready.text
    assert live.status_code == 200


def test_database_readiness_timeout_is_safe(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"database_health_timeout_seconds": 0.01})
    pool = FakePool(delay_seconds=0.1)
    app = create_app(settings, pool_factory=lambda _: pool)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "not_ready"


def test_configured_origin_receives_cors_header(app_client: TestClient) -> None:
    response = app_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_is_not_allowed(app_client: TestClient) -> None:
    response = app_client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_openapi_describes_operational_routes_without_secret_fields(
    app_client: TestClient,
) -> None:
    document = app_client.get("/openapi.json").json()

    assert "/health" in document["paths"]
    assert "/ready" in document["paths"]
    serialized = str(document).lower()
    for forbidden in ("password_hash", "token_hash", "encrypted_secret"):
        assert forbidden not in serialized

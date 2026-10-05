from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient


class NoopPool:
    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[NoopConnection]:
        yield NoopConnection()


class NoopConnection:
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield


@pytest.fixture
def rate_limited_client(test_settings: Settings) -> Iterator[TestClient]:
    settings = test_settings.model_copy(
        update={
            "auth_rate_limit_requests": 2,
            "auth_rate_limit_window_seconds": 60,
            "password_reset_rate_limit_requests": 1,
            "password_reset_rate_limit_window_seconds": 300,
        }
    )
    app = create_app(settings, pool_factory=lambda _: NoopPool())
    with TestClient(app) as client:
        yield client


def test_login_attempts_are_limited_with_safe_correlated_response(
    rate_limited_client: TestClient,
) -> None:
    for _ in range(2):
        response = rate_limited_client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    limited = rate_limited_client.post(
        "/api/v1/auth/login",
        json={},
        headers={"X-Request-ID": "login-limit-test"},
    )

    assert limited.status_code == 429
    assert limited.json() == {
        "code": "rate_limited",
        "message": "Too many authentication attempts. Try again later.",
        "field_errors": None,
        "request_id": "login-limit-test",
    }
    assert int(limited.headers["Retry-After"]) > 0
    assert limited.headers["X-Request-ID"] == "login-limit-test"


def test_password_reset_request_and_confirmation_share_a_stricter_limit(
    rate_limited_client: TestClient,
) -> None:
    first = rate_limited_client.post("/api/v1/auth/password-reset", json={})
    assert first.status_code == 422

    limited = rate_limited_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={},
        headers={"Origin": "http://localhost:5173"},
    )

    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth_rate_limit_requests", 0),
        ("auth_rate_limit_window_seconds", 0),
        ("password_reset_rate_limit_requests", 0),
        ("password_reset_rate_limit_window_seconds", 0),
    ],
)
def test_rate_limit_settings_must_be_positive(
    field: str,
    value: int,
    test_settings: Settings,
) -> None:
    with pytest.raises(ValueError):
        Settings(**{**test_settings.model_dump(), field: value})

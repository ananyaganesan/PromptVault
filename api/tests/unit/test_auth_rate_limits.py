from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from math import ceil
from time import monotonic

import pytest
from api.app.auth_rate_limits import (
    LocalRateLimitStore,
    enforce_email_verification_resend_limit,
)
from api.app.config import Settings
from api.app.errors import AppError
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


class SharedRateLimitStore:
    def __init__(self) -> None:
        self.hits: dict[str, list[float]] = {}

    async def retry_after(self, key: str, requests: int, window_seconds: int) -> int | None:
        now = monotonic()
        hits = self.hits.setdefault(key, [])
        hits[:] = [hit for hit in hits if hit > now - window_seconds]
        if len(hits) >= requests:
            return max(1, ceil(window_seconds - (now - hits[0])))
        hits.append(now)
        return None

    async def close(self) -> None:
        return None


class CapturingRateLimitStore(LocalRateLimitStore):
    def __init__(self) -> None:
        super().__init__(clock=lambda: 0.0)
        self.keys: list[str] = []

    async def retry_after(
        self, key: str, requests: int, window_seconds: int
    ) -> int | None:
        self.keys.append(key)
        return await super().retry_after(key, requests, window_seconds)


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


def test_two_api_instances_share_the_configured_rate_limit_store(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(
        update={"auth_rate_limit_requests": 1, "auth_rate_limit_window_seconds": 60}
    )
    store = SharedRateLimitStore()
    first_app = create_app(
        settings,
        pool_factory=lambda _: NoopPool(),
        rate_limit_store=store,
    )
    second_app = create_app(
        settings,
        pool_factory=lambda _: NoopPool(),
        rate_limit_store=store,
    )

    with TestClient(first_app) as first, TestClient(second_app) as second:
        assert first.post("/api/v1/auth/login", json={}).status_code == 422
        assert second.post("/api/v1/auth/login", json={}).status_code == 429


@pytest.mark.asyncio
async def test_verification_resend_composite_limit_allows_five_then_retries() -> None:
    store = CapturingRateLimitStore()

    for _ in range(5):
        await enforce_email_verification_resend_limit(
            store,
            client_host="203.0.113.10",
            normalized_email="alex@example.com",
            requests=5,
            window_seconds=3600,
        )

    with pytest.raises(AppError) as captured:
        await enforce_email_verification_resend_limit(
            store,
            client_host="203.0.113.10",
            normalized_email="alex@example.com",
            requests=5,
            window_seconds=3600,
        )

    assert captured.value.status_code == 429
    assert captured.value.code == "rate_limited"
    assert captured.value.headers == {"Retry-After": "3600"}
    assert all("alex@example.com" not in key for key in store.keys)


@pytest.mark.asyncio
async def test_verification_resend_limit_is_independent_by_client_and_email() -> None:
    store = LocalRateLimitStore(clock=lambda: 0.0)

    for _ in range(5):
        await enforce_email_verification_resend_limit(
            store,
            client_host="203.0.113.10",
            normalized_email="first@example.com",
            requests=5,
            window_seconds=3600,
        )
    await enforce_email_verification_resend_limit(
        store,
        client_host="203.0.113.10",
        normalized_email="second@example.com",
        requests=5,
        window_seconds=3600,
    )
    await enforce_email_verification_resend_limit(
        store,
        client_host="203.0.113.11",
        normalized_email="first@example.com",
        requests=5,
        window_seconds=3600,
    )


def test_two_api_instances_expose_the_same_injected_store_for_resend_routes(
    test_settings: Settings,
) -> None:
    store = SharedRateLimitStore()
    first_app = create_app(
        test_settings,
        pool_factory=lambda _: NoopPool(),
        rate_limit_store=store,
    )
    second_app = create_app(
        test_settings,
        pool_factory=lambda _: NoopPool(),
        rate_limit_store=store,
    )

    assert first_app.state.rate_limit_store is store
    assert second_app.state.rate_limit_store is store


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

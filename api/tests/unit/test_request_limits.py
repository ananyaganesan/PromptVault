from collections.abc import Iterator
from typing import Any

import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.request_limits import RequestBodyLimitMiddleware
from fastapi import Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send


class NoopPool:
    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def limited_client(test_settings: Settings) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"max_request_body_bytes": 32})
    app = create_app(settings, pool_factory=lambda _: NoopPool())

    @app.post("/echo-size")
    async def echo_size(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    with TestClient(app) as client:
        yield client


def test_request_body_at_limit_reaches_endpoint(limited_client: TestClient) -> None:
    response = limited_client.post(
        "/echo-size",
        content=b"x" * 32,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200
    assert response.json() == {"size": 32}


def test_oversized_request_returns_safe_correlated_error(
    limited_client: TestClient,
) -> None:
    response = limited_client.post(
        "/echo-size",
        content=b"super-secret-body-that-must-not-be-returned",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Request-ID": "oversized-request-test",
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "code": "request_too_large",
        "message": "Request body is too large",
        "field_errors": None,
        "request_id": "oversized-request-test",
    }
    assert "super-secret" not in response.text
    assert response.headers["X-Request-ID"] == "oversized-request-test"


def test_oversized_response_includes_cors_for_allowed_origin(
    limited_client: TestClient,
) -> None:
    response = limited_client.post(
        "/echo-size",
        content=b"x" * 33,
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 413
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.parametrize("content_length", ["invalid", "-1"])
def test_invalid_content_length_uses_public_error_envelope(
    limited_client: TestClient, content_length: str
) -> None:
    response = limited_client.post(
        "/echo-size",
        content=b"x",
        headers={"Content-Length": content_length, "X-Request-ID": "bad-length-test"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "bad_request",
        "message": "Content-Length is invalid",
        "field_errors": None,
        "request_id": "bad-length-test",
    }
    assert response.headers["X-Request-ID"] == "bad-length-test"


@pytest.mark.asyncio
async def test_chunked_body_stops_receiving_as_soon_as_limit_is_exceeded() -> None:
    inner_called = False
    receive_calls = 0
    sent: list[Message] = []
    messages: list[Message] = [
        {"type": "http.request", "body": b"x" * 16, "more_body": True},
        {"type": "http.request", "body": b"y" * 17, "more_body": True},
        {"type": "http.request", "body": b"must-not-be-read", "more_body": False},
    ]

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal inner_called
        inner_called = True

    async def receive() -> Message:
        nonlocal receive_calls
        message = messages[receive_calls]
        receive_calls += 1
        return message

    async def send(message: Message) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    middleware = RequestBodyLimitMiddleware(inner, max_bytes=32)

    await middleware(scope, receive, send)  # type: ignore[arg-type]

    assert inner_called is False
    assert receive_calls == 2
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413

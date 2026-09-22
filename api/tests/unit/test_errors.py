import logging
from collections.abc import Iterator

import pytest
from api.app.config import Settings
from api.app.dependencies.request_context import get_request_id
from api.app.errors import AppError
from api.app.main import create_app
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class NoopPool:
    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None


class Details(BaseModel):
    count: int = Field(gt=0)


class ValidationPayload(BaseModel):
    details: Details


def build_test_app(settings: Settings):
    app = create_app(settings, pool_factory=lambda _: NoopPool())

    @app.get("/__test__/request-id")
    def request_id(request: Request) -> dict[str, str]:
        return {"request_id": get_request_id(request)}

    @app.get("/__test__/conflict")
    def conflict() -> None:
        raise AppError(409, "conflict", "Resource already changed")

    @app.post("/__test__/validate")
    def validate(payload: ValidationPayload) -> ValidationPayload:
        return payload

    @app.get("/__test__/explode")
    def explode() -> None:
        raise RuntimeError("database-password")

    @app.get("/__test__/unauthorized")
    def unauthorized() -> None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return app


@pytest.fixture
def app_client(test_settings: Settings) -> Iterator[TestClient]:
    with TestClient(build_test_app(test_settings)) as client:
        yield client


@pytest.fixture
def app_client_no_raise(test_settings: Settings) -> Iterator[TestClient]:
    with TestClient(build_test_app(test_settings), raise_server_exceptions=False) as client:
        yield client


def test_generated_request_id_is_shared_by_header_and_context(app_client: TestClient) -> None:
    response = app_client.get("/__test__/request-id")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_valid_client_request_id_is_preserved(app_client: TestClient) -> None:
    response = app_client.get("/__test__/request-id", headers={"X-Request-ID": "client-123"})

    assert response.headers["X-Request-ID"] == "client-123"


@pytest.mark.parametrize("bad_id", ["", "x" * 129, "contains space"])
def test_invalid_request_id_is_replaced(app_client: TestClient, bad_id: str) -> None:
    response = app_client.get("/__test__/request-id", headers={"X-Request-ID": bad_id})

    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.headers["X-Request-ID"] != bad_id


def test_app_error_uses_contract_envelope(app_client: TestClient) -> None:
    response = app_client.get("/__test__/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "code": "conflict",
        "message": "Resource already changed",
        "field_errors": None,
        "request_id": response.headers["X-Request-ID"],
    }


def test_validation_error_uses_nested_field_paths_without_input(app_client: TestClient) -> None:
    response = app_client.post(
        "/__test__/validate",
        json={"details": {"count": "private-invalid-value"}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "body.details.count" in body["field_errors"]
    assert "private-invalid-value" not in response.text


def test_http_exception_preserves_authentication_challenge(app_client: TestClient) -> None:
    response = app_client.get("/__test__/unauthorized")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "unauthorized"


def test_unhandled_exception_is_redacted_and_logged_with_request_id(
    app_client_no_raise: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="promptvault.error"):
        response = app_client_no_raise.get("/__test__/explode")

    assert response.status_code == 500
    assert response.json()["message"] == "An unexpected error occurred"
    assert "database-password" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    matching_records = [
        record
        for record in caplog.records
        if getattr(record, "request_id", None) == response.headers["X-Request-ID"]
    ]
    assert len(matching_records) == 1
    assert matching_records[0].exception_type == "RuntimeError"
    assert "database-password" not in matching_records[0].getMessage()

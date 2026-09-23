"""Safe public error envelopes and FastAPI exception handlers."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.app.dependencies.request_context import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger("promptvault.error")
_ERROR_RESPONSE_DESCRIPTIONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Content",
}


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] | None = None
    request_id: str


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Describe the application's real public error envelope in OpenAPI."""

    return {
        status_code: {
            "model": ErrorEnvelope,
            "description": _ERROR_RESPONSE_DESCRIPTIONS.get(status_code, "Error Response"),
        }
        for status_code in status_codes
    }


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, list[str]] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors
        self.headers = dict(headers or {})


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    field_errors: dict[str, list[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        field_errors=field_errors,
        request_id=request_id,
    )
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=response_headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        field_errors=exc.field_errors,
        headers=exc.headers,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"])
        field_errors.setdefault(field, []).append(error["msg"])
    invalid_filter = any(error["loc"] and error["loc"][0] == "query" for error in exc.errors())
    return _error_response(
        request,
        status_code=400 if invalid_filter else 422,
        code="invalid_filter" if invalid_filter else "validation_error",
        message="Query filter is invalid" if invalid_filter else "Request is invalid",
        field_errors=field_errors,
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict"}
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "Request failed"
    return _error_response(
        request,
        status_code=exc.status_code,
        code=codes.get(exc.status_code, "bad_request"),
        message=message,
        headers=exc.headers,
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request)
    logger.error(
        "Unhandled API exception",
        extra={"request_id": request_id, "exception_type": type(exc).__name__},
    )
    return _error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred",
    )


def install_exception_handlers(application: FastAPI) -> None:
    # FastAPI's registration API types all handlers as accepting Exception, while
    # dispatch preserves the narrower registered exception class at runtime.
    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(
        RequestValidationError,
        validation_error_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        StarletteHTTPException,
        http_error_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(Exception, internal_error_handler)

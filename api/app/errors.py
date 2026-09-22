"""Safe public error envelopes and FastAPI exception handlers."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.app.dependencies.request_context import REQUEST_ID_HEADER, get_request_id


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] | None = None
    request_id: str


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    field_errors: dict[str, list[str]] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        field_errors=field_errors,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={REQUEST_ID_HEADER: request_id},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        field_errors=exc.field_errors,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"])
        field_errors.setdefault(field, []).append(error["msg"])
    return _error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request is invalid",
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
    )


async def internal_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred",
    )


def install_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_exception_handler(Exception, internal_error_handler)

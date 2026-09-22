"""Request correlation ID handling."""

import re
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[\x21-\x7e]{1,128}$")


def _new_request_id() -> str:
    return f"req_{uuid4().hex}"


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = _new_request_id()
        request.state.request_id = request_id
    return request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = (
            supplied if _VALID_REQUEST_ID.fullmatch(supplied) else _new_request_id()
        )
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

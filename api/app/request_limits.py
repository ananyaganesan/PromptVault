"""Bounded ASGI request-body enforcement with the public error envelope."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.app.dependencies.request_context import REQUEST_ID_HEADER, get_request_id


class RequestBodyLimitMiddleware:
    """Reject oversized bodies without buffering beyond the configured limit."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _error(self, scope: Scope, *, status_code: int, code: str, message: str) -> JSONResponse:
        request_id = get_request_id(Request(scope))
        return JSONResponse(
            status_code=status_code,
            content={
                "code": code,
                "message": message,
                "field_errors": None,
                "request_id": request_id,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )

    def _too_large(self, scope: Scope) -> JSONResponse:
        return self._error(
            scope,
            status_code=413,
            code="request_too_large",
            message="Request body is too large",
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_content_length = int(content_length)
                if parsed_content_length < 0:
                    raise ValueError
            except ValueError:
                response = self._error(
                    scope,
                    status_code=400,
                    code="bad_request",
                    message="Content-Length is invalid",
                )
                await response(scope, receive, send)
                return
            if parsed_content_length > self.max_bytes:
                await self._too_large(scope)(scope, receive, send)
                return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                buffered.append(message)
                break
            body = message.get("body", b"")
            if total + len(body) > self.max_bytes:
                await self._too_large(scope)(scope, receive, send)
                return
            total += len(body)
            buffered.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

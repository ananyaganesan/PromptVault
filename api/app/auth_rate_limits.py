"""Process-local throttling for authentication and password-reset endpoints."""

from collections import deque
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic
from typing import NamedTuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.app.dependencies.request_context import REQUEST_ID_HEADER, get_request_id


class Limit(NamedTuple):
    group: str
    requests: int
    window_seconds: int


class AuthRateLimitMiddleware:
    """Bound sensitive auth attempts per direct client and endpoint group.

    This deliberately uses the ASGI peer address rather than trusting forwarded
    headers. A production reverse proxy must preserve the actual client address
    or enforce its own distributed limit.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_requests: int,
        auth_window_seconds: int,
        reset_requests: int,
        reset_window_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.app = app
        self.clock = clock
        self.limits = {
            "/api/v1/auth/login": Limit(
                "authentication", auth_requests, auth_window_seconds
            ),
            "/api/v1/auth/register": Limit(
                "authentication", auth_requests, auth_window_seconds
            ),
            "/api/v1/auth/password-reset": Limit(
                "password-reset", reset_requests, reset_window_seconds
            ),
            "/api/v1/auth/password-reset/confirm": Limit(
                "password-reset", reset_requests, reset_window_seconds
            ),
        }
        self.hits: dict[tuple[str, str], deque[float]] = {}
        self.lock = Lock()

    def _retry_after(self, scope: Scope, limit: Limit) -> int | None:
        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        key = (client_host, limit.group)
        current = self.clock()
        cutoff = current - limit.window_seconds
        with self.lock:
            hits = self.hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit.requests:
                return max(1, ceil(limit.window_seconds - (current - hits[0])))
            hits.append(current)
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return
        retry_after = self._retry_after(scope, limit)
        if retry_after is None:
            await self.app(scope, receive, send)
            return

        request_id = get_request_id(Request(scope))
        response = JSONResponse(
            status_code=429,
            content={
                "code": "rate_limited",
                "message": "Too many authentication attempts. Try again later.",
                "field_errors": None,
                "request_id": request_id,
            },
            headers={
                REQUEST_ID_HEADER: request_id,
                "Retry-After": str(retry_after),
            },
        )
        await response(scope, receive, send)

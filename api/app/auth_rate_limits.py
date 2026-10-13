"""Local or distributed throttling for authentication and password-reset endpoints."""

from collections import deque
from collections.abc import Callable
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic
from typing import NamedTuple, Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.app.dependencies.request_context import REQUEST_ID_HEADER, get_request_id
from api.app.errors import AppError


class Limit(NamedTuple):
    group: str
    requests: int
    window_seconds: int


class RateLimitStore(Protocol):
    async def retry_after(
        self, key: str, requests: int, window_seconds: int
    ) -> int | None: ...

    async def close(self) -> None: ...


class LocalRateLimitStore:
    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.hits: dict[str, deque[float]] = {}
        self.lock = Lock()

    async def retry_after(
        self, key: str, requests: int, window_seconds: int
    ) -> int | None:
        current = self.clock()
        cutoff = current - window_seconds
        with self.lock:
            hits = self.hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= requests:
                return max(1, ceil(window_seconds - (current - hits[0])))
            hits.append(current)
        return None

    async def close(self) -> None:
        return None


_REDIS_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if count > tonumber(ARGV[2]) then
  return math.max(ttl, 1)
end
return 0
"""


class RedisRateLimitStore:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self.client = Redis.from_url(url, decode_responses=True)

    async def retry_after(
        self, key: str, requests: int, window_seconds: int
    ) -> int | None:
        result = await self.client.eval(
            _REDIS_LIMIT_SCRIPT,
            1,
            f"promptvault:rate-limit:{key}",
            window_seconds,
            requests,
        )
        retry_after = int(result)
        return retry_after if retry_after > 0 else None

    async def close(self) -> None:
        await self.client.aclose()


def create_rate_limit_store(redis_url: str | None) -> RateLimitStore:
    return RedisRateLimitStore(redis_url) if redis_url else LocalRateLimitStore()


async def enforce_email_verification_resend_limit(
    store: RateLimitStore,
    *,
    client_host: str,
    normalized_email: str,
    requests: int,
    window_seconds: int,
) -> None:
    email_hash = sha256(normalized_email.encode("utf-8")).hexdigest()
    retry_after = await store.retry_after(
        f"email-verification-resend:{client_host}:{email_hash}",
        requests,
        window_seconds,
    )
    if retry_after is not None:
        raise AppError(
            429,
            "rate_limited",
            "Too many verification email requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


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
        store: RateLimitStore | None = None,
    ) -> None:
        self.app = app
        self.store = store or LocalRateLimitStore(clock)
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
    async def _retry_after(self, scope: Scope, limit: Limit) -> int | None:
        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        return await self.store.retry_after(
            f"{limit.group}:{client_host}", limit.requests, limit.window_seconds
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return
        retry_after = await self._retry_after(scope, limit)
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

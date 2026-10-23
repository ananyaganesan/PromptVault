"""JWT authentication and active-user resolution."""

from typing import Annotated, cast

from api.app.db.orm import ORMConnection
from api.app.db.pool import PoolProtocol, get_pool
from api.app.db.transactions import DatabaseConnection, get_connection, get_snapshot_connection
from api.app.errors import AppError
from api.app.repositories.users import UserRecord, UserRepository
from api.app.security import ExpiredAccessToken, InvalidAccessToken, decode_access_token
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)
_BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}


async def _resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    connection: DatabaseConnection,
) -> UserRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "unauthorized", "Authentication is required", headers=_BEARER_HEADERS)
    try:
        claims = decode_access_token(credentials.credentials, request.app.state.settings)
    except ExpiredAccessToken as exc:
        raise AppError(
            401,
            "token_expired",
            "Access token has expired",
            headers=_BEARER_HEADERS,
        ) from exc
    except InvalidAccessToken as exc:
        raise AppError(
            401,
            "invalid_token",
            "Access token is invalid",
            headers=_BEARER_HEADERS,
        ) from exc

    repository = UserRepository(connection)
    if not await repository.is_session_active(claims.token_id, claims.user_id):
        raise AppError(401, "invalid_token", "Access token is invalid", headers=_BEARER_HEADERS)
    user = await repository.get_by_id(claims.user_id)
    if user is None:
        raise AppError(401, "invalid_token", "Access token is invalid", headers=_BEARER_HEADERS)
    if not user.is_active:
        raise AppError(403, "inactive_user", "User account is inactive")
    if user.role != claims.role:
        raise AppError(401, "invalid_token", "Access token is invalid", headers=_BEARER_HEADERS)
    return user


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> UserRecord:
    return await _resolve_current_user(request, credentials, connection)


async def get_detached_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    pool: Annotated[PoolProtocol, Depends(get_pool)],
) -> UserRecord:
    async with pool.connection() as raw_connection:
        connection = cast(ORMConnection, raw_connection)
        async with connection.transaction():
            return await _resolve_current_user(request, credentials, connection)


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]
DetachedCurrentUser = Annotated[UserRecord, Depends(get_detached_current_user)]


async def get_snapshot_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    connection: Annotated[DatabaseConnection, Depends(get_snapshot_connection)],
) -> UserRecord:
    return await _resolve_current_user(request, credentials, connection)


SnapshotCurrentUser = Annotated[UserRecord, Depends(get_snapshot_current_user)]

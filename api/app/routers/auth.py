"""Authentication HTTP endpoints."""

from typing import Annotated

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser, bearer_scheme
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import ErrorEnvelope
from api.app.repositories.users import UserRepository
from api.app.schemas.auth import (
    AccountCloseRequest,
    AccountExportResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
)
from api.app.schemas.users import ProfileUpdate, UserResponse
from api.app.security import decode_access_token
from api.app.services.auth import AuthService
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def get_auth_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> AuthService:
    return AuthService(UserRepository(connection), request.app.state.settings)


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorEnvelope}},
)
async def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    return await service.register(payload)


@router.post(
    "/login",
    response_model=SessionResponse,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    return await service.login(payload)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={401: {"model": ErrorEnvelope}},
)
async def logout(
    request: Request,
    current_user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    claims = decode_access_token(credentials.credentials, request.app.state.settings)
    await service.logout(session_id=claims.token_id, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/account/export",
    response_model=AccountExportResponse,
    responses={401: {"model": ErrorEnvelope}},
)
async def export_account(
    current_user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccountExportResponse:
    return await service.export_account(current_user)


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={401: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def close_account(
    payload: AccountCloseRequest,
    request: Request,
    current_user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.close_account(payload, current_user, get_request_id(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    responses={503: {"model": ErrorEnvelope}},
)
async def request_password_reset(
    payload: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await service.request_password_reset(payload)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={400: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    await service.reset_password(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
    dependencies=[Depends(allow_query_parameters())],
)
async def update_profile(
    payload: ProfileUpdate,
    request: Request,
    current_user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    claims = decode_access_token(credentials.credentials, request.app.state.settings)
    return await service.update_profile(
        payload, current_user, claims.token_id, get_request_id(request)
    )

"""Authentication HTTP endpoints."""

from typing import Annotated

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.errors import ErrorEnvelope
from api.app.repositories.users import UserRepository
from api.app.schemas.auth import LoginRequest, RegisterRequest, SessionResponse
from api.app.schemas.users import UserResponse
from api.app.services.auth import AuthService
from fastapi import APIRouter, Depends, Request, status

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


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)

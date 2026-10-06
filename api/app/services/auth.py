"""Authentication use cases."""

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from api.app.config import Settings
from api.app.email import EmailDeliveryError, send_password_reset_email
from api.app.errors import AppError
from api.app.repositories.users import UserRecord, UserRepository
from api.app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
)
from api.app.schemas.users import UserResponse
from api.app.security import (
    create_access_token,
    hash_one_time_token,
    hash_password,
    verify_password,
)
from psycopg.errors import UniqueViolation
from starlette.concurrency import run_in_threadpool

_BEARER_HEADERS = {"WWW-Authenticate": "Bearer"}


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def register(self, request: RegisterRequest) -> SessionResponse:
        encoded_password = await run_in_threadpool(
            hash_password,
            request.password.get_secret_value(),
        )
        try:
            user = await self.repository.create_user(
                email=str(request.email),
                display_name=request.display_name,
                password_hash=encoded_password,
            )
        except UniqueViolation as exc:
            raise AppError(
                409,
                "duplicate_email",
                "An account with this email already exists",
            ) from exc
        return self._session(user)

    async def login(self, request: LoginRequest) -> SessionResponse:
        user = await self.repository.get_by_email(str(request.email))
        if not user:
            raise AppError(
                401,
                "invalid_credentials",
                "Invalid email or password.",
                headers=_BEARER_HEADERS,
            )
        password_matches = await run_in_threadpool(
            verify_password,
            user.password_hash,
            request.password.get_secret_value(),
        )
        if not password_matches:
            raise AppError(
                401,
                "invalid_credentials",
                "Invalid email or password.",
                headers=_BEARER_HEADERS,
            )
        if not user.is_active:
            raise AppError(403, "inactive_user", "User account is inactive")
        return self._session(user)

    async def request_password_reset(self, request: PasswordResetRequest) -> None:
        if not self.settings.smtp_host:
            raise AppError(
                503,
                "email_delivery_unavailable",
                "Password reset email could not be delivered",
            )
        user = await self.repository.get_by_email(str(request.email))
        if user is None or not user.is_active:
            return

        token = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self.settings.password_reset_ttl_minutes
        )
        await self.repository.create_password_reset_token(
            user_id=user.id,
            token_hash=hash_one_time_token(token),
            expires_at=expires_at,
        )
        try:
            await run_in_threadpool(send_password_reset_email, self.settings, user.email, token)
        except EmailDeliveryError as exc:
            raise AppError(
                503,
                "email_delivery_unavailable",
                "Password reset email could not be delivered",
            ) from exc

    async def reset_password(self, request: PasswordResetConfirm) -> None:
        password_hash = await run_in_threadpool(
            hash_password,
            request.password.get_secret_value(),
        )
        consumed = await self.repository.consume_password_reset_token(
            token_hash=hash_one_time_token(request.token),
            password_hash=password_hash,
        )
        if not consumed:
            raise AppError(
                400,
                "invalid_reset_token",
                "Password reset link is invalid or expired",
            )

    def _session(self, user: UserRecord) -> SessionResponse:
        return SessionResponse(
            access_token=create_access_token(user.id, user.role, self.settings),
            expires_in=self.settings.access_token_ttl_minutes * 60,
            user=UserResponse.model_validate(user),
        )

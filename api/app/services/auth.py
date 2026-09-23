"""Authentication use cases."""

from api.app.config import Settings
from api.app.errors import AppError
from api.app.repositories.users import UserRecord, UserRepository
from api.app.schemas.auth import LoginRequest, RegisterRequest, SessionResponse
from api.app.schemas.users import UserResponse
from api.app.security import create_access_token, hash_password, verify_password
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
                "email_not_found",
                "Email address not found.",
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
                "invalid_password",
                "Incorrect password.",
                headers=_BEARER_HEADERS,
            )
        if not user.is_active:
            raise AppError(403, "inactive_user", "User account is inactive")
        return self._session(user)

    def _session(self, user: UserRecord) -> SessionResponse:
        return SessionResponse(
            access_token=create_access_token(user.id, user.role, self.settings),
            expires_in=self.settings.access_token_ttl_minutes * 60,
            user=UserResponse.model_validate(user),
        )

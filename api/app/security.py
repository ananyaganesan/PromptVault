"""Password hashing and signed application access tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from api.app.config import Settings

UserRole = Literal["user", "admin"]
_JWT_ALGORITHM = "HS256"
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


class InvalidAccessToken(ValueError):
    """Raised when an application JWT is malformed or untrusted."""


class ExpiredAccessToken(InvalidAccessToken):
    """Raised when an otherwise valid application JWT has expired."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    role: UserRole
    issued_at: datetime
    expires_at: datetime


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(encoded_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def hash_one_time_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: UUID,
    role: UserRole,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.access_token_ttl_minutes)
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role,
            "iat": issued_at,
            "exp": expires_at,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.secret_key,
        algorithm=_JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_JWT_ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require": ["sub", "role", "iat", "exp", "iss", "aud"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
        role = payload["role"]
        if role not in ("user", "admin"):
            raise InvalidAccessToken("invalid role claim")
        claims = AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            role=role,
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InvalidAccessToken):
            raise
        raise InvalidAccessToken("invalid access token") from exc

    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if claims.expires_at <= current_time:
        raise ExpiredAccessToken("access token expired")
    if claims.issued_at > current_time + timedelta(seconds=30):
        raise InvalidAccessToken("access token issued in the future")
    return claims

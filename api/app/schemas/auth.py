"""Authentication request and response schemas."""

from datetime import datetime
from typing import Annotated, Any

from api.app.schemas.users import UserResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

Password = Annotated[SecretStr, Field(min_length=1, max_length=128)]
RegistrationPassword = Annotated[SecretStr, Field(min_length=12, max_length=128)]


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Password

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class RegisterRequest(AuthRequest):
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    password: RegistrationPassword

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display name must not be blank")
        return normalized

    @field_validator("password")
    @classmethod
    def reject_password_whitespace(cls, value: SecretStr) -> SecretStr:
        if any(character.isspace() for character in value.get_secret_value()):
            raise ValueError("password must not contain whitespace")
        return value


class LoginRequest(AuthRequest):
    pass


class PendingVerificationResponse(BaseModel):
    email: EmailStr
    message: str


class EmailVerificationConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str


class EmailVerificationResendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=32, max_length=512)]
    password: RegistrationPassword

    @field_validator("password")
    @classmethod
    def reject_password_whitespace(cls, value: SecretStr) -> SecretStr:
        if any(character.isspace() for character in value.get_secret_value()):
            raise ValueError("password must not contain whitespace")
        return value


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class AccountCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: Password


class AccountExportResponse(BaseModel):
    generated_at: datetime
    profile: UserResponse
    owned_projects: list[dict[str, Any]]
    memberships: list[dict[str, Any]]
    prompt_versions: list[dict[str, Any]]
    runs: list[dict[str, Any]]
    deployments: list[dict[str, Any]]
    api_tokens: list[dict[str, Any]]

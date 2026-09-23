"""Authentication request and response schemas."""

from typing import Annotated

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


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

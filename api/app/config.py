"""Validated application configuration."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str = Field(repr=False)
    access_token_ttl_minutes: int = 30
    jwt_issuer: str = "promptvault"
    jwt_audience: str = "promptvault-web"
    api_port: int = 8000
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:5173",)
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout_seconds: float = 5.0
    database_health_timeout_seconds: float = 2.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    password_reset_ttl_minutes: int = 30
    password_reset_url: str = "http://localhost:5173/reset-password"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: str | None = None
    smtp_starttls: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_runtime_limits(self) -> Self:
        if (
            self.db_pool_min_size < 0
            or self.db_pool_max_size < 1
            or self.db_pool_max_size < self.db_pool_min_size
        ):
            raise ValueError("database pool sizes must satisfy 0 <= min <= max and max >= 1")
        if self.db_pool_timeout_seconds <= 0 or self.database_health_timeout_seconds <= 0:
            raise ValueError("database timeouts must be positive")
        if self.access_token_ttl_minutes <= 0:
            raise ValueError("access token lifetime must be positive")
        if self.password_reset_ttl_minutes <= 0:
            raise ValueError("password reset lifetime must be positive")
        if self.smtp_port < 1 or self.smtp_port > 65535:
            raise ValueError("SMTP port must be between 1 and 65535")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP username and password must be configured together")
        if self.smtp_host and not self.smtp_from_email:
            raise ValueError("SMTP_FROM_EMAIL is required when SMTP_HOST is configured")
        if self.environment == "production" and (
            self.secret_key == "change-me" or len(self.secret_key) < 32
        ):
            raise ValueError("production SECRET_KEY must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    # Required values are supplied by BaseSettings from the environment.
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()

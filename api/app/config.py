"""Validated application configuration."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str = Field(repr=False)
    provider_encryption_key: str | None = Field(default=None, repr=False)
    access_token_ttl_minutes: int = 30
    jwt_issuer: str = "promptvault"
    jwt_audience: str = "promptvault-web"
    api_port: int = 8000
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:5173",)
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout_seconds: float = 5.0
    database_health_timeout_seconds: float = 2.0
    provider_timeout_seconds: float = 30.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

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
        if (
            self.db_pool_timeout_seconds <= 0
            or self.database_health_timeout_seconds <= 0
            or self.provider_timeout_seconds <= 0
        ):
            raise ValueError("database and provider timeouts must be positive")
        if self.access_token_ttl_minutes <= 0:
            raise ValueError("access token lifetime must be positive")
        if self.environment == "production" and (
            self.secret_key == "change-me" or len(self.secret_key) < 32
        ):
            raise ValueError("production SECRET_KEY must be at least 32 characters")
        if self.environment == "production" and (
            self.provider_encryption_key is None
            or self.provider_encryption_key == "change-me-provider-encryption-key"
            or self.provider_encryption_key == self.secret_key
            or len(self.provider_encryption_key) < 32
        ):
            raise ValueError(
                "production PROVIDER_ENCRYPTION_KEY must be unique and at least 32 characters"
            )
        return self

    @property
    def resolved_provider_encryption_key(self) -> str:
        return self.provider_encryption_key or self.secret_key


@lru_cache
def get_settings() -> Settings:
    # Required values are supplied by BaseSettings from the environment.
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()

"""Validated application configuration."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str
    api_port: int = 8000
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:5173",)
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout_seconds: float = 5.0
    database_health_timeout_seconds: float = 2.0

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
        if self.db_pool_min_size < 0 or self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("database pool sizes must satisfy 0 <= min <= max")
        if self.db_pool_timeout_seconds <= 0 or self.database_health_timeout_seconds <= 0:
            raise ValueError("database timeouts must be positive")
        if self.environment == "production" and (
            self.secret_key == "change-me" or len(self.secret_key) < 32
        ):
            raise ValueError("production SECRET_KEY must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()

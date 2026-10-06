"""Validated application configuration."""

from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit values."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    database_role: Literal["promptvault_app"] | None = None
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
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    max_request_body_bytes: int = 1_048_576
    auth_rate_limit_requests: int = 10
    auth_rate_limit_window_seconds: int = 60
    password_reset_rate_limit_requests: int = 5
    password_reset_rate_limit_window_seconds: int = 300
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    password_reset_ttl_minutes: int = 30
    password_reset_url: str = "http://localhost:5173/reset-password"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: EmailStr | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout_seconds: float = 10.0

    @field_validator("database_role", mode="before")
    @classmethod
    def empty_database_role_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("smtp_host", "smtp_username", "smtp_from_email", mode="before")
    @classmethod
    def empty_smtp_values_are_unset(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("smtp_password", mode="before")
    @classmethod
    def empty_smtp_password_is_unset(cls, value: object) -> object:
        return None if value == "" else value

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
        if self.max_request_body_bytes <= 0:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be positive")
        if min(
            self.auth_rate_limit_requests,
            self.auth_rate_limit_window_seconds,
            self.password_reset_rate_limit_requests,
            self.password_reset_rate_limit_window_seconds,
        ) <= 0:
            raise ValueError("authentication rate limits must be positive")
        if self.password_reset_ttl_minutes <= 0:
            raise ValueError("PASSWORD_RESET_TTL_MINUTES must be positive")
        reset_url = urlsplit(self.password_reset_url)
        if (
            reset_url.scheme not in {"http", "https"}
            or not reset_url.netloc
            or reset_url.username is not None
            or reset_url.password is not None
            or reset_url.fragment
        ):
            raise ValueError(
                "PASSWORD_RESET_URL must be an absolute HTTP URL "
                "without credentials or a fragment"
            )
        if self.environment == "production" and self.smtp_host and reset_url.scheme != "https":
            raise ValueError("production PASSWORD_RESET_URL must use HTTPS when SMTP is enabled")
        if not 1 <= self.smtp_port <= 65535 or self.smtp_timeout_seconds <= 0:
            raise ValueError("SMTP_PORT and SMTP_TIMEOUT_SECONDS must be positive and valid")
        if bool(self.smtp_host) != bool(self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL must be configured together")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if self.smtp_username and not self.smtp_host:
            raise ValueError("SMTP_HOST is required for SMTP authentication")
        if self.smtp_ssl and self.smtp_starttls:
            raise ValueError("SMTP_SSL and SMTP_STARTTLS cannot both be enabled")
        if self.smtp_username and not (self.smtp_ssl or self.smtp_starttls):
            raise ValueError("SMTP authentication requires TLS")
        if self.environment == "production" and self.smtp_host and not (
            self.smtp_ssl or self.smtp_starttls
        ):
            raise ValueError("production SMTP delivery requires TLS")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain absolute HTTP origins")
            if self.environment == "production" and parsed.scheme != "https":
                raise ValueError("production CORS_ORIGINS must use HTTPS")
        if self.environment == "production" and (
            self.secret_key == "change-me" or len(self.secret_key) < 32
        ):
            raise ValueError("production SECRET_KEY must be at least 32 characters")
        gemini_url = urlsplit(self.gemini_api_base_url)
        if (
            gemini_url.scheme not in {"http", "https"}
            or not gemini_url.netloc
            or gemini_url.username is not None
            or gemini_url.password is not None
            or gemini_url.query
            or gemini_url.fragment
        ):
            raise ValueError("GEMINI_API_BASE_URL must be an absolute HTTP URL")
        if self.environment == "production" and gemini_url.scheme != "https":
            raise ValueError("production GEMINI_API_BASE_URL must use HTTPS")
        if self.environment == "production" and self.database_role != "promptvault_app":
            raise ValueError("production DATABASE_ROLE must be promptvault_app")
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

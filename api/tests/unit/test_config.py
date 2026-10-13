from pathlib import Path

import pytest
from api.app.config import Settings
from pydantic import ValidationError

BASE = {
    "_env_file": None,
    "database_url": "postgresql://promptvault:promptvault@localhost:5432/promptvault",
    "secret_key": "test-secret-that-is-long-enough",
}


def test_settings_tests_ignore_local_smtp_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "SMTP_HOST=smtp.example.com\nSMTP_FROM_EMAIL=sender@example.com\n"
        "PASSWORD_RESET_URL=http://localhost:5173/reset-password\n",
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        **{
            **BASE,
            "environment": "production",
            "secret_key": "production-secret-that-is-at-least-32-characters",
            "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
            "cors_origins": "https://app.example.com",
            "database_role": "promptvault_app",
            "rate_limit_redis_url": "redis://redis:6379/0",
        }
    )
    assert settings.smtp_host is None


def test_settings_parse_comma_separated_cors_origins() -> None:
    settings = Settings(**BASE, cors_origins="http://localhost:5173, https://app.example.com")

    assert settings.cors_origins == (
        "http://localhost:5173",
        "https://app.example.com",
    )


def test_settings_reject_invalid_pool_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, db_pool_min_size=10, db_pool_max_size=2)


def test_settings_reject_zero_maximum_pool_size() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, db_pool_min_size=0, db_pool_max_size=0)


def test_settings_reject_nonpositive_provider_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, provider_timeout_seconds=0)


def test_settings_reject_nonpositive_execution_concurrency_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, max_concurrent_runs_per_user=0)


def test_settings_reject_nonpositive_request_body_limit() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, max_request_body_bytes=0)


@pytest.mark.parametrize(
    "cors_origins",
    ["*", "http://example.com/path", "not-an-origin"],
)
def test_settings_reject_unsafe_cors_origins(cors_origins: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, cors_origins=cors_origins)


def test_production_requires_https_cors_origins() -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
        "cors_origins": "http://app.example.com",
    }

    with pytest.raises(ValidationError):
        Settings(**values)


def test_production_rejects_placeholder_secret() -> None:
    values = {**BASE, "environment": "production", "secret_key": "change-me"}

    with pytest.raises(ValidationError):
        Settings(**values)


def test_settings_representation_redacts_secret() -> None:
    provider_key = "provider-encryption-key-at-least-32-characters"
    settings = Settings(**BASE, provider_encryption_key=provider_key)

    assert BASE["secret_key"] not in repr(settings)
    assert provider_key not in repr(settings)


def test_production_requires_dedicated_provider_encryption_key() -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
    }

    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize(
    "provider_encryption_key",
    [
        "change-me-provider-encryption-key",
        "production-secret-that-is-at-least-32-characters",
    ],
)
def test_production_rejects_placeholder_or_reused_provider_key(
    provider_encryption_key: str,
) -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": provider_encryption_key,
    }

    with pytest.raises(ValidationError):
        Settings(**values)


def test_production_accepts_independent_provider_encryption_key() -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
        "cors_origins": "https://app.example.com",
        "database_role": "promptvault_app",
        "rate_limit_redis_url": "redis://redis:6379/0",
    }

    settings = Settings(**values)

    assert settings.environment == "production"


@pytest.mark.parametrize("database_role", [None, "postgres"])
def test_production_requires_restricted_application_database_role(
    database_role: str | None,
) -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
        "cors_origins": "https://app.example.com",
        "database_role": database_role,
    }

    with pytest.raises(ValidationError):
        Settings(**values)


def test_production_requires_https_gemini_api_base_url() -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
        "cors_origins": "https://app.example.com",
        "database_role": "promptvault_app",
        "rate_limit_redis_url": "redis://redis:6379/0",
        "gemini_api_base_url": "http://gemini.example.com/v1beta",
    }

    with pytest.raises(ValidationError, match="GEMINI_API_BASE_URL"):
        Settings(**values)


def test_production_requires_distributed_rate_limit_store() -> None:
    values = {
        **BASE,
        "environment": "production",
        "secret_key": "production-secret-that-is-at-least-32-characters",
        "provider_encryption_key": "independent-provider-key-that-is-at-least-32-characters",
        "cors_origins": "https://app.example.com",
        "database_role": "promptvault_app",
    }

    with pytest.raises(ValidationError, match="RATE_LIMIT_REDIS_URL"):
        Settings(**values)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.deepseek.com/v1",
        "https://other-provider.example/v1",
        "https://generativelanguage.googleapis.com:8443/v1beta",
    ],
)
def test_production_cannot_redirect_gemini_to_another_provider(url: str) -> None:
    with pytest.raises(ValueError, match="official Gemini host"):
        Settings(
            environment="production",
            database_url="postgresql://app:password@db/promptvault",
            database_role="promptvault_app",
            secret_key="production-test-secret-at-least-32-characters",
            provider_encryption_key="independent-provider-key-at-least-32-characters",
            cors_origins="https://app.example.com",
            rate_limit_redis_url="redis://redis:6379/0",
            gemini_api_base_url=url,
            _env_file=None,
        )


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_project_cannot_replace_gemini_with_another_provider(environment: str) -> None:
    with pytest.raises(ValueError, match="official Gemini host"):
        Settings(
            **{
                **BASE,
                "environment": environment,
                "gemini_api_base_url": "https://api.deepseek.com/v1",
            }
        )


def test_email_verification_settings_have_safe_local_defaults() -> None:
    settings = Settings(**BASE)

    assert settings.email_verification_url == "http://localhost:5173/verify-email"
    assert settings.email_verification_ttl_minutes == 30
    assert settings.email_verification_resend_cooldown_seconds == 60
    assert settings.email_verification_resend_limit == 5
    assert settings.email_verification_resend_window_seconds == 3600


@pytest.mark.parametrize(
    "field",
    [
        "email_verification_ttl_minutes",
        "email_verification_resend_cooldown_seconds",
        "email_verification_resend_limit",
        "email_verification_resend_window_seconds",
    ],
)
def test_email_verification_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError, match="email verification limits"):
        Settings(**BASE, **{field: 0})


@pytest.mark.parametrize(
    "url",
    [
        "ftp://app.example.com/verify-email",
        "https://user:password@app.example.com/verify-email",
        "https://app.example.com/verify-email#token",
        "not-a-url",
    ],
)
def test_email_verification_url_must_be_a_safe_absolute_http_url(url: str) -> None:
    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_URL"):
        Settings(**BASE, email_verification_url=url)


def test_production_with_smtp_requires_https_email_verification_url() -> None:
    with pytest.raises(ValidationError, match="EMAIL_VERIFICATION_URL"):
        Settings(
            **{
                **BASE,
                "environment": "production",
                "secret_key": "production-secret-that-is-at-least-32-characters",
                "provider_encryption_key": (
                    "independent-provider-key-that-is-at-least-32-characters"
                ),
                "cors_origins": "https://app.example.com",
                "database_role": "promptvault_app",
                "rate_limit_redis_url": "redis://redis:6379/0",
                "smtp_host": "smtp.example.com",
                "smtp_from_email": "sender@example.com",
                "password_reset_url": "https://app.example.com/reset-password",
                "email_verification_url": "http://localhost:5173/verify-email",
                "project_invitation_url": "https://app.example.com/project-invitations",
            }
        )


def test_production_without_smtp_keeps_local_email_verification_url_usable() -> None:
    settings = Settings(
        **{
            **BASE,
            "environment": "production",
            "secret_key": "production-secret-that-is-at-least-32-characters",
            "provider_encryption_key": (
                "independent-provider-key-that-is-at-least-32-characters"
            ),
            "cors_origins": "https://app.example.com",
            "database_role": "promptvault_app",
            "rate_limit_redis_url": "redis://redis:6379/0",
        }
    )

    assert settings.email_verification_url == "http://localhost:5173/verify-email"

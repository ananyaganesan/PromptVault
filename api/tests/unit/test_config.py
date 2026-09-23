import pytest
from api.app.config import Settings
from pydantic import ValidationError

BASE = {
    "database_url": "postgresql://promptvault:promptvault@localhost:5432/promptvault",
    "secret_key": "test-secret-that-is-long-enough",
}


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


def test_production_rejects_placeholder_secret() -> None:
    values = {**BASE, "environment": "production", "secret_key": "change-me"}

    with pytest.raises(ValidationError):
        Settings(**values)


def test_settings_representation_redacts_secret() -> None:
    settings = Settings(**BASE)

    assert BASE["secret_key"] not in repr(settings)


def test_settings_require_smtp_credentials_as_a_pair() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, smtp_username="username")

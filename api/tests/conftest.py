import os

import pytest
from api.app.config import Settings

os.environ.setdefault(
    "DATABASE_URL", "postgresql://promptvault:promptvault@localhost:5432/promptvault_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-that-is-long-enough")


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault_test",
        secret_key="test-secret-that-is-long-enough",
        _env_file=None,
    )

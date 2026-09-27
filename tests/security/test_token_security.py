"""JWT and runtime-token trust boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from api.app.config import Settings
from api.app.security import (
    ExpiredAccessToken,
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    generate_runtime_token,
    hash_runtime_token,
)


def test_runtime_tokens_are_random_prefixed_and_only_hash_to_lookup_values() -> None:
    first = generate_runtime_token()
    second = generate_runtime_token()

    assert first.startswith("pv_live_")
    assert first != second
    assert len(hash_runtime_token(first)) == 64
    assert first not in hash_runtime_token(first)


def test_access_tokens_fail_on_tamper_expiry_and_wrong_audience() -> None:
    settings = Settings(
        environment="test",
        database_url="postgresql://localhost/test",
        secret_key="test-secret-that-is-at-least-32-characters",
        _env_file=None,
    )
    issued = datetime(2026, 9, 26, tzinfo=UTC)
    token = create_access_token(uuid4(), "user", settings, now=issued)
    header, payload, signature = token.split(".")
    replacement = "a" if signature[0] != "a" else "b"
    tampered = ".".join((header, payload, replacement + signature[1:]))

    with pytest.raises(ExpiredAccessToken):
        decode_access_token(token, settings, now=issued + timedelta(hours=1))
    with pytest.raises(InvalidAccessToken):
        decode_access_token(tampered, settings, now=issued + timedelta(minutes=1))
    with pytest.raises(InvalidAccessToken):
        decode_access_token(
            token,
            settings.model_copy(update={"jwt_audience": "another-service"}),
            now=issued + timedelta(minutes=1),
        )

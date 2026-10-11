from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from api.app.config import Settings
from api.app.security import (
    ExpiredAccessToken,
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    hash_one_time_token,
    hash_password,
    verify_password,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_password_hash_uses_argon2id_and_verifies_only_the_original_password() -> None:
    encoded = hash_password("CorrectHorse2026!")

    assert encoded.startswith("$argon2id$")
    assert "CorrectHorse2026!" not in encoded
    assert verify_password(encoded, "CorrectHorse2026!") is True
    assert verify_password(encoded, "wrong-password") is False


def test_invalid_password_hash_fails_closed() -> None:
    assert verify_password("not-an-argon2-hash", "CorrectHorse2026!") is False


def test_one_time_token_hash_is_deterministic_and_does_not_expose_the_token() -> None:
    token = "reset-token-value"

    digest = hash_one_time_token(token)

    assert digest == hash_one_time_token(token)
    assert len(digest) == 64
    assert token not in digest


def test_access_token_round_trip_contains_required_identity_claims(
    test_settings: Settings,
) -> None:
    issued_at = datetime(2026, 9, 23, 10, 30, tzinfo=UTC)
    token_id = uuid4()

    token = create_access_token(
        USER_ID, "user", test_settings, now=issued_at, token_id=token_id
    )
    claims = decode_access_token(
        token,
        test_settings,
        now=issued_at + timedelta(minutes=1),
    )

    assert claims.user_id == USER_ID
    assert claims.token_id == token_id
    assert claims.role == "user"
    assert claims.issued_at == issued_at
    assert claims.expires_at == issued_at + timedelta(
        minutes=test_settings.access_token_ttl_minutes
    )


def test_expired_access_token_has_distinct_failure(test_settings: Settings) -> None:
    issued_at = datetime(2026, 9, 23, 10, 30, tzinfo=UTC)
    token = create_access_token(USER_ID, "user", test_settings, now=issued_at)

    with pytest.raises(ExpiredAccessToken):
        decode_access_token(
            token,
            test_settings,
            now=issued_at + timedelta(hours=2),
        )


def test_tampered_access_token_is_rejected(test_settings: Settings) -> None:
    token = create_access_token(USER_ID, "user", test_settings)
    replacement = "a" if token[-1] != "a" else "b"

    with pytest.raises(InvalidAccessToken):
        decode_access_token(token[:-1] + replacement, test_settings)

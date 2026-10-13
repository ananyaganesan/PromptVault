from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.email import EmailDeliveryError
from api.app.main import create_app
from api.app.security import (
    create_access_token,
    hash_one_time_token,
    hash_password,
    verify_password,
)
from fastapi.testclient import TestClient

SEEDED_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
DELIVERED_VERIFICATION_TOKENS: dict[str, list[str]] = {}


@pytest.fixture(scope="module")
def auth_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "smtp_host": "smtp.test",
            "smtp_from_email": "no-reply@promptvault.dev",
        }
    )
    app = create_app(settings)

    def capture_verification_email(_settings: Settings, recipient: str, token: str) -> None:
        DELIVERED_VERIFICATION_TOKENS.setdefault(recipient, []).append(token)

    with patch(
        "api.app.services.auth.send_email_verification_email",
        capture_verification_email,
        create=True,
    ), TestClient(app) as client:
        yield client


def registration_payload(email: str) -> dict[str, str]:
    return {
        "email": email,
        "password": "CorrectHorse2026!",
        "display_name": "Alex Morgan",
    }


def register_verify_login(
    client: TestClient,
    email: str,
    *,
    password: str = "CorrectHorse2026!",
) -> dict[str, object]:
    payload = registration_payload(email) | {"password": password}
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 202, registered.text
    token = DELIVERED_VERIFICATION_TOKENS[email][-1]
    confirmed = client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": token}
    )
    assert confirmed.status_code == 204, confirmed.text
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200, logged_in.text
    return logged_in.json()


@pytest.mark.database
def test_register_creates_pending_account_without_session_and_hashes_token(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"register-{uuid4()}@example.com"

    registered = auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email.upper())
    )

    assert registered.status_code == 202
    assert registered.json() == {
        "email": email,
        "message": "Check your email to verify your account",
    }
    assert "access_token" not in registered.text
    assert "password" not in registered.text.lower()
    raw_token = DELIVERED_VERIFICATION_TOKENS[email][-1]
    with psycopg.connect(seeded_database_url) as connection:
        pending = connection.execute(
            """
            SELECT u.email_verified_at, t.token_hash, t.used_at
            FROM users u
            JOIN email_verification_tokens t ON t.user_id = u.id
            WHERE u.email = %s
            """,
            (email,),
        ).fetchone()
    assert pending == (None, sha256(raw_token.encode()).hexdigest(), None)
    assert raw_token not in registered.text


@pytest.mark.database
def test_register_rejects_role_escalation_field(auth_client: TestClient) -> None:
    payload = registration_payload(f"role-{uuid4()}@example.com")
    payload["role"] = "admin"

    response = auth_client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.database
def test_register_rejects_whitespace_in_password(auth_client: TestClient) -> None:
    payload = registration_payload(f"spaces-{uuid4()}@example.com")
    payload["password"] = "Short       123"

    response = auth_client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.database
def test_register_returns_duplicate_email_conflict_case_insensitively(
    auth_client: TestClient,
) -> None:
    email = f"duplicate-{uuid4()}@example.com"
    first = auth_client.post("/api/v1/auth/register", json=registration_payload(email))
    assert first.status_code == 202

    duplicate = registration_payload(email.upper())
    response = auth_client.post("/api/v1/auth/register", json=duplicate)

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_email"
    assert response.json()["message"] == "An account with this email already exists"
    assert "constraint" not in response.text.lower()


@pytest.mark.database
def test_registration_delivery_failure_rolls_back_pending_account(
    auth_client: TestClient,
    seeded_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"delivery-failure-{uuid4()}@example.com"

    def fail_delivery(*_: object) -> None:
        raise EmailDeliveryError("SMTP delivery failed")

    monkeypatch.setattr("api.app.services.auth.send_email_verification_email", fail_delivery)
    response = auth_client.post("/api/v1/auth/register", json=registration_payload(email))

    assert response.status_code == 503
    assert response.json()["code"] == "email_delivery_unavailable"
    with psycopg.connect(seeded_database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM users WHERE email = %s", (email,)
        ).fetchone() == (0,)


@pytest.mark.database
def test_login_reveals_pending_state_only_after_correct_password(
    auth_client: TestClient,
) -> None:
    email = f"pending-login-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202

    correct = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email.upper(), "password": "CorrectHorse2026!"},
    )
    wrong = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword2026!"},
    )

    assert correct.status_code == 403
    assert correct.json()["code"] == "email_unverified"
    assert correct.json()["message"] == "Verify your email before signing in"
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_credentials"


@pytest.mark.database
def test_confirmation_verifies_once_then_allows_login(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"confirm-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    token = DELIVERED_VERIFICATION_TOKENS[email][-1]

    confirmed = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": token}
    )
    reused = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": token}
    )
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "CorrectHorse2026!"},
    )

    assert confirmed.status_code == 204
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_verification_token"
    assert login.status_code == 200
    with psycopg.connect(seeded_database_url) as connection:
        state = connection.execute(
            """
            SELECT u.email_verified_at IS NOT NULL, t.used_at IS NOT NULL
            FROM users u
            JOIN email_verification_tokens t ON t.user_id = u.id
            WHERE u.email = %s
            """,
            (email,),
        ).fetchone()
    assert state == (True, True)


@pytest.mark.database
@pytest.mark.parametrize("invalid_reason", ["malformed", "unknown", "expired"])
def test_confirmation_hides_malformed_unknown_and_expired_token_details(
    auth_client: TestClient,
    seeded_database_url: str,
    invalid_reason: str,
) -> None:
    token = "too-short" if invalid_reason == "malformed" else uuid4().hex + uuid4().hex
    if invalid_reason == "expired":
        email = f"expired-verification-{uuid4()}@example.com"
        assert auth_client.post(
            "/api/v1/auth/register", json=registration_payload(email)
        ).status_code == 202
        token = DELIVERED_VERIFICATION_TOKENS[email][-1]
        with psycopg.connect(seeded_database_url) as connection:
            connection.execute(
                "UPDATE email_verification_tokens SET expires_at = now() - interval '1 minute' "
                "WHERE token_hash = %s",
                (hash_one_time_token(token),),
            )

    response = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": token}
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_verification_token",
        "message": "Email verification link is invalid or expired",
        "field_errors": None,
        "request_id": response.json()["request_id"],
    }


@pytest.mark.database
def test_verification_token_cannot_reset_password(
    auth_client: TestClient,
) -> None:
    email = f"token-boundary-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    token = DELIVERED_VERIFICATION_TOKENS[email][-1]

    response = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "ReplacementPassword2026!"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


@pytest.mark.database
def test_concurrent_confirmation_has_one_successful_transition(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"confirmation-race-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    token = DELIVERED_VERIFICATION_TOKENS[email][-1]

    def confirm(_: int):
        return auth_client.post(
            "/api/v1/auth/email-verification/confirm", json={"token": token}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(confirm, range(2)))

    assert sorted(response.status_code for response in responses) == [204, 400]
    with psycopg.connect(seeded_database_url) as connection:
        assert connection.execute(
            "SELECT email_verified_at IS NOT NULL FROM users WHERE email = %s", (email,)
        ).fetchone() == (True,)


@pytest.mark.database
@pytest.mark.parametrize(
    "email",
    [
        "missing-resend@example.com",
        "inactive@promptvault.dev",
        "user@promptvault.dev",
    ],
)
def test_resend_hides_unknown_inactive_and_verified_accounts(
    auth_client: TestClient,
    email: str,
) -> None:
    delivered_before = sum(len(tokens) for tokens in DELIVERED_VERIFICATION_TOKENS.values())

    response = auth_client.post(
        "/api/v1/auth/email-verification/resend",
        json={"email": email.upper()},
    )

    assert response.status_code == 202
    assert response.json() == {
        "message": "If this account is awaiting verification, we sent a new link."
    }
    assert sum(len(tokens) for tokens in DELIVERED_VERIFICATION_TOKENS.values()) == delivered_before


@pytest.mark.database
def test_resend_replaces_old_link_and_only_new_link_can_verify(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"resend-replace-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    old_token = DELIVERED_VERIFICATION_TOKENS[email][-1]
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "UPDATE email_verification_tokens SET created_at = now() - interval '61 seconds' "
            "WHERE token_hash = %s",
            (hash_one_time_token(old_token),),
        )

    resent = auth_client.post(
        "/api/v1/auth/email-verification/resend", json={"email": email.upper()}
    )
    new_token = DELIVERED_VERIFICATION_TOKENS[email][-1]
    old_confirmation = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": old_token}
    )
    new_confirmation = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": new_token}
    )

    assert resent.status_code == 202
    assert new_token != old_token
    assert old_confirmation.status_code == 400
    assert old_confirmation.json()["code"] == "invalid_verification_token"
    assert new_confirmation.status_code == 204


@pytest.mark.database
def test_immediate_resend_returns_account_cooldown_hint(auth_client: TestClient) -> None:
    email = f"resend-cooldown-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202

    response = auth_client.post(
        "/api/v1/auth/email-verification/resend", json={"email": email}
    )

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert 1 <= int(response.headers["Retry-After"]) <= 60


@pytest.mark.database
def test_six_eligible_resends_trigger_hourly_composite_limit(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"resend-hourly-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202

    for _ in range(5):
        with psycopg.connect(seeded_database_url) as connection:
            connection.execute(
                "UPDATE email_verification_tokens SET created_at = now() - interval '61 seconds' "
                "WHERE user_id = (SELECT id FROM users WHERE email = %s)",
                (email,),
            )
        response = auth_client.post(
            "/api/v1/auth/email-verification/resend", json={"email": email}
        )
        assert response.status_code == 202, response.text

    limited = auth_client.post(
        "/api/v1/auth/email-verification/resend", json={"email": email}
    )

    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert int(limited.headers["Retry-After"]) > 60


@pytest.mark.database
def test_resend_delivery_failure_preserves_prior_usable_token(
    auth_client: TestClient,
    seeded_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"resend-delivery-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    old_token = DELIVERED_VERIFICATION_TOKENS[email][-1]
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "UPDATE email_verification_tokens SET created_at = now() - interval '61 seconds' "
            "WHERE token_hash = %s",
            (hash_one_time_token(old_token),),
        )

    def fail_delivery(*_: object) -> None:
        raise EmailDeliveryError("SMTP delivery failed")

    monkeypatch.setattr("api.app.services.auth.send_email_verification_email", fail_delivery)
    response = auth_client.post(
        "/api/v1/auth/email-verification/resend", json={"email": email}
    )
    old_confirmation = auth_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": old_token}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "email_delivery_unavailable"
    assert old_confirmation.status_code == 204


@pytest.mark.database
def test_racing_resends_create_only_one_active_replacement(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"resend-race-{uuid4()}@example.com"
    assert auth_client.post(
        "/api/v1/auth/register", json=registration_payload(email)
    ).status_code == 202
    original_delivery_count = len(DELIVERED_VERIFICATION_TOKENS[email])
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "UPDATE email_verification_tokens SET created_at = now() - interval '61 seconds' "
            "WHERE user_id = (SELECT id FROM users WHERE email = %s)",
            (email,),
        )

    def resend(_: int):
        return auth_client.post(
            "/api/v1/auth/email-verification/resend", json={"email": email}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(resend, range(2)))

    assert sorted(response.status_code for response in responses) == [202, 429]
    assert len(DELIVERED_VERIFICATION_TOKENS[email]) == original_delivery_count + 1
    with psycopg.connect(seeded_database_url) as connection:
        active_tokens = connection.execute(
            """
            SELECT count(*)
            FROM email_verification_tokens
            WHERE user_id = (SELECT id FROM users WHERE email = %s) AND used_at IS NULL
            """,
            (email,),
        ).fetchone()
    assert active_tokens == (1,)


@pytest.mark.database
def test_login_accepts_seeded_credentials(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "USER@PROMPTVAULT.DEV",
            "password": "UserDemo2026!",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "user@promptvault.dev"


@pytest.mark.database
def test_logout_revokes_the_server_side_session(auth_client: TestClient) -> None:
    email = f"logout-{uuid4()}@example.com"
    session = register_verify_login(auth_client, email)
    token = session["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert auth_client.post("/api/v1/auth/logout", headers=headers).status_code == 204

    rejected = auth_client.get("/api/v1/auth/me", headers=headers)
    assert rejected.status_code == 401
    assert rejected.json()["code"] == "invalid_token"


@pytest.mark.database
def test_account_export_excludes_secrets_and_closure_pseudonymizes_identity(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"lifecycle-{uuid4()}@example.com"
    payload = registration_payload(email)
    session = register_verify_login(auth_client, email, password=payload["password"])
    user_id = session["user"]["id"]
    token = session["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    exported = auth_client.get("/api/v1/auth/account/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["profile"]["email"] == email
    assert exported.json()["owned_projects"] == []
    for forbidden in ("password_hash", "token_hash", "access_token"):
        assert forbidden not in exported.text

    wrong_password = auth_client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers=headers,
        json={"password": "WrongPassword2026!"},
    )
    assert wrong_password.status_code == 401
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 200

    closed = auth_client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers=headers,
        json={"password": payload["password"]},
    )
    assert closed.status_code == 204
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": payload["password"]},
    ).status_code == 401

    with psycopg.connect(seeded_database_url) as connection:
        account = connection.execute(
            "SELECT email, display_name, role, is_active FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT after_data FROM audit_events
            WHERE entity_type = 'accounts' AND entity_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert account[0].endswith("@invalid.promptvault")
    assert account[1:] == ("Deleted User", "user", False)
    assert audit[0]["pseudonymized"] is True
    assert email not in str(audit[0])


@pytest.mark.database
def test_password_reset_revokes_every_existing_session(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"reset-sessions-{uuid4()}@example.com"
    password = registration_payload(email)["password"]
    registered = register_verify_login(auth_client, email, password=password)
    second = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert second.status_code == 200
    tokens = [registered["access_token"], second.json()["access_token"]]
    delivered: list[str] = []
    monkeypatch.setattr(
        "api.app.services.auth.send_password_reset_email",
        lambda _settings, _recipient, token: delivered.append(token),
    )
    password_changed_recipients: list[str] = []
    monkeypatch.setattr(
        "api.app.services.auth.send_password_changed_email",
        lambda _settings, recipient: password_changed_recipients.append(recipient),
    )

    assert auth_client.post("/api/v1/auth/password-reset", json={"email": email}).status_code == 202
    confirmed = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": delivered[0], "password": "ReplacementPassword2026!"},
    )
    assert confirmed.status_code == 204
    assert password_changed_recipients == [email]

    for token in tokens:
        rejected = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rejected.status_code == 401
        assert rejected.json()["code"] == "invalid_token"


@pytest.mark.database
def test_password_reset_delivers_a_one_time_link_and_updates_the_password(
    auth_client: TestClient,
    seeded_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered_tokens: list[tuple[str, str]] = []
    new_password = f"NewPassword-{uuid4().hex}!"

    def capture_reset_email(_settings: Settings, recipient: str, token: str) -> None:
        delivered_tokens.append((recipient, token))

    monkeypatch.setattr("api.app.services.auth.send_password_reset_email", capture_reset_email)
    password_changed_recipients: list[str] = []
    monkeypatch.setattr(
        "api.app.services.auth.send_password_changed_email",
        lambda _settings, recipient: password_changed_recipients.append(recipient),
    )
    requested = auth_client.post(
        "/api/v1/auth/password-reset",
        json={"email": "user@promptvault.dev"},
    )

    assert requested.status_code == 202
    assert delivered_tokens[0][0] == "user@promptvault.dev"

    try:
        confirmed = auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": delivered_tokens[0][1], "password": new_password},
        )
        assert confirmed.status_code == 204
        assert password_changed_recipients == ["user@promptvault.dev"]

        login = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "user@promptvault.dev", "password": new_password},
        )
        assert login.status_code == 200

        reused = auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": delivered_tokens[0][1], "password": "AnotherPassword2026!"},
        )
        assert reused.status_code == 400
        assert reused.json()["code"] == "invalid_reset_token"
    finally:
        with psycopg.connect(seeded_database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (hash_password("UserDemo2026!"), SEEDED_USER_ID),
            )


@pytest.mark.database
def test_password_reset_does_not_disclose_an_unknown_account(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[str] = []
    monkeypatch.setattr(
        "api.app.services.auth.send_password_reset_email",
        lambda _settings, recipient, _token: delivered.append(recipient),
    )

    response = auth_client.post(
        "/api/v1/auth/password-reset",
        json={"email": f"missing-{uuid4()}@example.com"},
    )

    assert response.status_code == 202
    assert delivered == []


@pytest.mark.database
def test_reset_rejects_current_and_older_passwords_without_consuming_link(
    auth_client: TestClient,
    seeded_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"history-{uuid4()}@example.com"
    original, second, third = "OriginalPassword2026!", "SecondPassword2026!", "ThirdPassword2026!"
    session = register_verify_login(auth_client, email, password=original)
    user_id = session["user"]["id"]
    tokens: list[str] = []
    monkeypatch.setattr(
        "api.app.services.auth.send_password_reset_email",
        lambda _settings, _recipient, token: tokens.append(token),
    )

    def request_link() -> str:
        assert (
            auth_client.post("/api/v1/auth/password-reset", json={"email": email}).status_code
            == 202
        )
        return tokens[-1]

    def confirm(token: str, password: str):
        return auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "password": password},
        )

    token = request_link()
    assert confirm(token, original).json()["code"] == "password_reused"
    assert confirm(token, second).status_code == 204
    assert (
        auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": original},
        ).status_code
        == 401
    )
    token = request_link()
    for reused in (original, second):
        result = confirm(token, reused)
        assert result.status_code == 409
        assert result.json()["code"] == "password_reused"
        with psycopg.connect(seeded_database_url) as connection:
            assert connection.execute(
                "SELECT used_at FROM password_reset_tokens WHERE token_hash = %s",
                (hash_one_time_token(token),),
            ).fetchone() == (None,)
    assert confirm(token, third).status_code == 204
    assert confirm(token, "FourthPassword2026!").json()["code"] == "invalid_reset_token"
    assert (
        auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": third},
        ).status_code
        == 200
    )
    with psycopg.connect(seeded_database_url) as connection:
        hashes = [
            row[0]
            for row in connection.execute(
                "SELECT password_hash FROM password_history WHERE user_id = %s",
                (user_id,),
            ).fetchall()
        ]
    assert len(hashes) == 3
    assert all(encoded.startswith("$argon2id$") for encoded in hashes)
    assert all(
        any(verify_password(encoded, password) for encoded in hashes)
        for password in (original, second, third)
    )


@pytest.mark.database
def test_concurrent_resets_cannot_both_accept_the_same_new_password(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"history-race-{uuid4()}@example.com"
    session = register_verify_login(auth_client, email)
    user_id = session["user"]["id"]
    tokens = [uuid4().hex + uuid4().hex for _ in range(2)]
    with psycopg.connect(seeded_database_url) as connection:
        for token in tokens:
            connection.execute(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
                "VALUES (%s, %s, now() + interval '30 minutes')",
                (user_id, hash_one_time_token(token)),
            )

    def confirm(token: str):
        return auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "password": "ConcurrentNewPassword2026!"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(confirm, tokens))
    assert sorted(response.status_code for response in responses) == [204, 409]
    assert (
        next(response for response in responses if response.status_code == 409).json()["code"]
        == "password_reused"
    )
    with psycopg.connect(seeded_database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM password_history WHERE user_id = %s",
            (user_id,),
        ).fetchone() == (2,)


@pytest.mark.database
@pytest.mark.parametrize("invalid_reason", ["expired", "inactive"])
def test_invalid_reset_cannot_change_password_or_history(
    auth_client: TestClient,
    seeded_database_url: str,
    invalid_reason: str,
) -> None:
    email = f"history-invalid-{uuid4()}@example.com"
    session = register_verify_login(auth_client, email)
    user_id = session["user"]["id"]
    token = uuid4().hex + uuid4().hex
    with psycopg.connect(seeded_database_url) as connection:
        expires_at = datetime.now(UTC) + timedelta(
            minutes=-1 if invalid_reason == "expired" else 30,
        )
        connection.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, %s)",
            (user_id, hash_one_time_token(token), expires_at),
        )
        if invalid_reason == "inactive":
            connection.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,))
    response = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "FreshPassword2026!"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"
    with psycopg.connect(seeded_database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM password_history WHERE user_id = %s",
            (user_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT used_at FROM password_reset_tokens WHERE token_hash = %s",
            (hash_one_time_token(token),),
        ).fetchone() == (None,)


@pytest.mark.database
@pytest.mark.parametrize(
    ("email", "password", "code", "message"),
    [
        (
            "user@promptvault.dev",
            "WrongPassword2026!",
            "invalid_credentials",
            "Invalid email or password.",
        ),
        ("user@promptvault.dev", "User@123", "invalid_credentials", "Invalid email or password."),
        (
            "missing-user@example.com",
            "WrongPassword2026!",
            "invalid_credentials",
            "Invalid email or password.",
        ),
    ],
)
def test_login_rejects_invalid_credentials_without_disclosing_which_field(
    auth_client: TestClient,
    email: str,
    password: str,
    code: str,
    message: str,
) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json()["code"] == code
    assert response.json()["message"] == message
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.database
def test_inactive_user_cannot_login(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    with psycopg.connect(seeded_database_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE users SET is_active = FALSE WHERE id = %s",
            (SEEDED_USER_ID,),
        )
    try:
        response = auth_client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@promptvault.dev",
                "password": "UserDemo2026!",
            },
        )
    finally:
        with psycopg.connect(seeded_database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE users SET is_active = TRUE WHERE id = %s",
                (SEEDED_USER_ID,),
            )

    assert response.status_code == 403
    assert response.json()["code"] == "inactive_user"


@pytest.mark.database
def test_me_requires_valid_unexpired_token(
    auth_client: TestClient,
    test_settings: Settings,
) -> None:
    missing = auth_client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.json()["code"] == "unauthorized"
    assert missing.headers["www-authenticate"] == "Bearer"

    token = create_access_token(SEEDED_USER_ID, "user", test_settings)
    replacement = "a" if token[-1] != "a" else "b"
    tampered = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token[:-1] + replacement}"},
    )
    assert tampered.status_code == 401
    assert tampered.json()["code"] == "invalid_token"

    expired = create_access_token(
        SEEDED_USER_ID,
        "user",
        test_settings,
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    expired_response = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert expired_response.status_code == 401
    assert expired_response.json()["code"] == "token_expired"


@pytest.mark.database
def test_existing_token_stops_working_when_user_is_deactivated(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "user@promptvault.dev", "password": "UserDemo2026!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    with psycopg.connect(seeded_database_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE users SET is_active = FALSE WHERE id = %s",
            (SEEDED_USER_ID,),
        )
    try:
        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        with psycopg.connect(seeded_database_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE users SET is_active = TRUE WHERE id = %s",
                (SEEDED_USER_ID,),
            )

    assert response.status_code == 403
    assert response.json()["code"] == "inactive_user"

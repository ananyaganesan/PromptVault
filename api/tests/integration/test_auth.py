from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.security import create_access_token, hash_one_time_token, hash_password
from fastapi.testclient import TestClient

SEEDED_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(scope="module")
def auth_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def registration_payload(email: str) -> dict[str, str]:
    return {
        "email": email,
        "password": "CorrectHorse2026!",
        "display_name": "Alex Morgan",
    }


@pytest.mark.database
def test_register_returns_user_session_and_me_resolves_database_user(
    auth_client: TestClient,
) -> None:
    email = f"register-{uuid4()}@example.com"

    registered = auth_client.post("/api/v1/auth/register", json=registration_payload(email))

    assert registered.status_code == 201
    session = registered.json()
    assert session["token_type"] == "bearer"
    assert session["expires_in"] == 1800
    assert session["user"]["email"] == email
    assert session["user"]["role"] == "user"
    assert "password" not in registered.text.lower()

    current = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert current.status_code == 200
    assert current.json() == session["user"]


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
    assert first.status_code == 201

    duplicate = registration_payload(email.upper())
    response = auth_client.post("/api/v1/auth/register", json=duplicate)

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_email"
    assert "constraint" not in response.text.lower()


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
def test_password_reset_delivers_a_one_time_link_and_updates_the_password(
    auth_client: TestClient,
    seeded_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered_tokens: list[tuple[str, str]] = []

    def capture_reset_email(_settings: Settings, recipient: str, token: str) -> None:
        delivered_tokens.append((recipient, token))

    monkeypatch.setattr("api.app.services.auth.send_password_reset_email", capture_reset_email)
    requested = auth_client.post(
        "/api/v1/auth/password-reset",
        json={"email": "user@promptvault.dev"},
    )

    assert requested.status_code == 202
    assert delivered_tokens[0][0] == "user@promptvault.dev"

    try:
        confirmed = auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": delivered_tokens[0][1], "password": "NewPassword2026!"},
        )
        assert confirmed.status_code == 204

        login = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "user@promptvault.dev", "password": "NewPassword2026!"},
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
    monkeypatch.setattr(auth_client.app.state.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(auth_client.app.state.settings, "smtp_from_email", "no-reply@example.com")
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
def test_expired_password_reset_token_cannot_change_the_password(
    auth_client: TestClient,
    seeded_database_url: str,
) -> None:
    token = f"expired-reset-token-{uuid4()}"
    token_hash = hash_one_time_token(token)
    with psycopg.connect(seeded_database_url, autocommit=True) as connection:
        connection.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP - INTERVAL '1 minute')
            """,
            (SEEDED_USER_ID, token_hash),
        )
    try:
        response = auth_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "password": "ExpiredToken2026!"},
        )
    finally:
        with psycopg.connect(seeded_database_url, autocommit=True) as connection:
            connection.execute(
                "DELETE FROM password_reset_tokens WHERE token_hash = %s",
                (token_hash,),
            )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


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

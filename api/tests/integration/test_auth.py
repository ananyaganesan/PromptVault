from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.security import (
    create_access_token,
    hash_one_time_token,
    hash_password,
    verify_password,
)
from fastapi.testclient import TestClient

SEEDED_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


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
    new_password = f"NewPassword-{uuid4().hex}!"

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
            json={"token": delivered_tokens[0][1], "password": new_password},
        )
        assert confirmed.status_code == 204

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
    payload = registration_payload(email) | {"password": original}
    registered = auth_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]
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
    registered = auth_client.post("/api/v1/auth/register", json=registration_payload(email))
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]
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
    registered = auth_client.post("/api/v1/auth/register", json=registration_payload(email))
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]
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

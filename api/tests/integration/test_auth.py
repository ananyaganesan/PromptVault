from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.security import create_access_token
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
@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("user@promptvault.dev", "WrongPassword2026!"),
        ("missing-user@example.com", "WrongPassword2026!"),
    ],
)
def test_login_invalid_credentials_are_generic_and_challenge_bearer(
    auth_client: TestClient,
    email: str,
    password: str,
) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["message"] == "Invalid email or password"
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

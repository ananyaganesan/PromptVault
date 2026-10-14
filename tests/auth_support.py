"""Authentication helpers limited to isolated test databases."""

from typing import cast
from urllib.parse import unquote, urlparse
from uuid import uuid4

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app.security import hash_password

_TEST_PASSWORD = "CorrectHorse2026!"


def create_verified_test_user(
    client: TestClient, label: str
) -> tuple[dict[str, object], dict[str, str]]:
    """Insert a verified test user and obtain a session through the public API."""

    app = cast(FastAPI, client.app)
    database_url = str(app.state.settings.database_url)
    database_name = unquote(urlparse(database_url).path.lstrip("/")).split("?", 1)[0]
    if not database_name.endswith("_test"):
        raise RuntimeError("test database name must end in _test")

    email = f"{label}-{uuid4().hex}@example.com"
    display_name = label.replace("-", " ").title()
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            """
            INSERT INTO users (
                email, display_name, password_hash, role, is_active, email_verified_at
            )
            VALUES (%s, %s, %s, 'user', TRUE, CURRENT_TIMESTAMP)
            """,
            (email, display_name, hash_password(_TEST_PASSWORD)),
        )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    session = response.json()
    return session["user"], {"Authorization": f"Bearer {session['access_token']}"}

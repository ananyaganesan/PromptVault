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


def seed_owned_project(
    client: TestClient, headers: dict[str, str], payload: dict[str, object]
) -> dict[str, object]:
    """Seed an owned project for downstream tests, not an ordinary-user POST permission."""
    from psycopg.rows import dict_row

    actor = client.get("/api/v1/auth/me", headers=headers)
    assert actor.status_code == 200
    app = cast(FastAPI, client.app)
    database_url = str(app.state.settings.database_url)
    if not unquote(urlparse(database_url).path).endswith("_test"):
        raise RuntimeError("Project fixtures require an isolated _test database")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute(
            "SELECT set_config('app.user_id',%s,true),set_config('app.request_id','test-fixture',true)",
            (actor.json()["id"],),
        )
        row = connection.execute(
            "INSERT INTO projects(name,key,description,owner_id) VALUES (%s,%s,%s,%s) RETURNING id",
            (
                payload["name"],
                payload["key"],
                payload.get("description"),
                actor.json()["id"],
            ),
        ).fetchone()
    result = client.get(f"/api/v1/projects/{row['id']}", headers=headers)
    assert result.status_code == 200
    return result.json()

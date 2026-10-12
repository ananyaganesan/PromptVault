import pytest
from fastapi.testclient import TestClient

from tests.support import register


@pytest.mark.database
def test_display_name_update_is_self_only_and_persists(api_client: TestClient) -> None:
    owner, headers = register(api_client, "profile-owner")
    outsider, outsider_headers = register(api_client, "profile-outsider")
    response = api_client.patch(
        "/api/v1/auth/me", headers=headers, json={"display_name": "  Ananya Ganesan  "}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == owner["id"] and updated["display_name"] == "Ananya Ganesan"
    assert updated["email"] == owner["email"] and updated["role"] == "user"
    assert "password_hash" not in updated
    assert api_client.get("/api/v1/auth/me", headers=headers).json() == updated
    assert (
        api_client.get("/api/v1/auth/me", headers=outsider_headers).json()[
            "display_name"
        ]
        == outsider["display_name"]
    )


@pytest.mark.database
@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": " "},
        {"display_name": "x" * 121},
        {"display_name": "Name", "role": "admin"},
        {"display_name": "Name", "email": "other@example.com"},
        {"display_name": "Name", "user_id": "11111111-1111-4111-8111-111111111111"},
        {"display_name": "Name", "is_active": False},
    ],
)
def test_profile_security_fields_and_invalid_names_are_rejected(
    api_client: TestClient,
    payload: dict[str, object],
) -> None:
    owner, headers = register(api_client, "profile-invalid")
    assert (
        api_client.patch("/api/v1/auth/me", headers=headers, json=payload).status_code
        == 422
    )
    assert (
        api_client.get("/api/v1/auth/me", headers=headers).json()["display_name"]
        == owner["display_name"]
    )


@pytest.mark.database
def test_profile_rejects_anonymous_and_logged_out_sessions(
    api_client: TestClient,
) -> None:
    payload = {"display_name": "Name"}
    assert api_client.patch("/api/v1/auth/me", json=payload).status_code == 401
    _, headers = register(api_client, "profile-logout")
    assert api_client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert (
        api_client.patch("/api/v1/auth/me", headers=headers, json=payload).status_code
        == 401
    )


@pytest.mark.database
def test_profile_function_works_without_broad_user_update_privilege(
    api_client: TestClient,
    db_connection,
) -> None:
    from psycopg.errors import InsufficientPrivilege

    from api.app.security import decode_access_token

    owner, headers = register(api_client, "restricted-profile")
    claims = decode_access_token(
        headers["Authorization"].removeprefix("Bearer "), api_client.app.state.settings
    )
    db_connection.execute("SET LOCAL ROLE promptvault_app")
    with pytest.raises(InsufficientPrivilege), db_connection.transaction():
        db_connection.execute(
            "UPDATE users SET role='admin' WHERE id=%s", (owner["id"],)
        )
    row = db_connection.execute(
        "SELECT display_name, role FROM update_self_display_name(%s, %s, %s, %s)",
        (owner["id"], claims.token_id, "Restricted profile", "profile-test"),
    ).fetchone()
    assert row == {"display_name": "Restricted profile", "role": "user"}

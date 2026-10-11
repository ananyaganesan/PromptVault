from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.dependencies.authorization import ProjectMember, ProjectOwner, SuperAdmin
from api.app.main import create_app
from api.app.security import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def install_test_routes(app: FastAPI) -> None:
    @app.get("/_test/admin")
    async def admin_only(user: SuperAdmin) -> dict[str, str]:
        return {"user_id": str(user.id)}

    @app.get("/_test/projects/{project_id}/member")
    async def member_only(project_id: UUID, user: ProjectMember) -> dict[str, str]:
        return {"project_id": str(project_id), "user_id": str(user.id)}

    @app.get("/_test/projects/{project_id}/owner")
    async def owner_only(project_id: UUID, user: ProjectOwner) -> dict[str, str]:
        return {"project_id": str(project_id), "user_id": str(user.id)}


@pytest.fixture(scope="module")
def authorization_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    app = create_app(settings)
    install_test_routes(app)
    with TestClient(app) as client:
        yield client


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.database
def test_unregistered_forged_admin_session_is_rejected(
    authorization_client: TestClient,
    test_settings: Settings,
) -> None:
    forged_role_token = create_access_token(USER_ID, "admin", test_settings)

    response = authorization_client.get(
        "/_test/admin",
        headers={"Authorization": f"Bearer {forged_role_token}"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


@pytest.mark.database
def test_active_database_admin_passes_admin_guard(
    authorization_client: TestClient,
) -> None:
    token = login(authorization_client, "admin@promptvault.dev", "AdminDemo2026!")

    response = authorization_client.get(
        "/_test/admin",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


@pytest.mark.database
def test_project_owner_passes_member_and_owner_guards(
    authorization_client: TestClient,
) -> None:
    token = login(authorization_client, "user@promptvault.dev", "UserDemo2026!")
    headers = {"Authorization": f"Bearer {token}"}

    member = authorization_client.get(f"/_test/projects/{PROJECT_ID}/member", headers=headers)
    owner = authorization_client.get(f"/_test/projects/{PROJECT_ID}/owner", headers=headers)

    assert member.status_code == 200
    assert owner.status_code == 200


@pytest.mark.database
def test_member_cannot_use_owner_guard_and_outsider_cannot_use_either_guard(
    authorization_client: TestClient,
    seeded_database_url: str,
) -> None:
    email = f"member-{uuid4()}@example.com"
    session = authorization_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "CorrectHorse2026!",
            "display_name": "Project Member",
        },
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    outsider_member = authorization_client.get(
        f"/_test/projects/{PROJECT_ID}/member", headers=headers
    )
    outsider_owner = authorization_client.get(
        f"/_test/projects/{PROJECT_ID}/owner", headers=headers
    )
    assert outsider_member.status_code == 403
    assert outsider_owner.status_code == 403

    with psycopg.connect(seeded_database_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO project_members (project_id, user_id, added_by) VALUES (%s, %s, %s)",
            (PROJECT_ID, session["user"]["id"], USER_ID),
        )

    member = authorization_client.get(f"/_test/projects/{PROJECT_ID}/member", headers=headers)
    owner = authorization_client.get(f"/_test/projects/{PROJECT_ID}/owner", headers=headers)

    assert member.status_code == 200
    assert owner.status_code == 403


@pytest.mark.database
def test_admin_bypasses_project_membership_and_ownership_guards(
    authorization_client: TestClient,
) -> None:
    token = login(authorization_client, "admin@promptvault.dev", "AdminDemo2026!")
    headers = {"Authorization": f"Bearer {token}"}
    unknown_project = uuid4()

    member = authorization_client.get(
        f"/_test/projects/{unknown_project}/member", headers=headers
    )
    owner = authorization_client.get(
        f"/_test/projects/{unknown_project}/owner", headers=headers
    )

    assert member.status_code == 200
    assert owner.status_code == 200

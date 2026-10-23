"""Admin project creation and invitation-only user access policy."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient
from tests.auth_support import create_verified_test_user
from tests.invitation_support import TOKENS


@pytest.fixture(scope="module")
def project_policy_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    with TestClient(create_app(settings)) as client:
        from tests.provider_support import seed_gemini_test_credential
        seed_gemini_test_credential(client.app.state.settings)
        yield client


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.database
def test_only_admin_creates_and_user_access_requires_emailed_invitation(
    project_policy_client: TestClient,
) -> None:
    user, user_headers = create_verified_test_user(project_policy_client, "project-invite-only")
    admin_headers = _admin_headers(project_policy_client)
    payload = {"name": "Invitation-only Workspace", "key": f"invite-only-{uuid4().hex}"}

    denied = project_policy_client.post(
        "/api/v1/projects", headers=user_headers, json=payload
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "forbidden"

    created = project_policy_client.post(
        "/api/v1/projects", headers=admin_headers, json=payload
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["owner"]["id"] != user["id"]

    project_path = f"/api/v1/projects/{project['id']}"
    assert project_policy_client.get(project_path, headers=user_headers).status_code == 403
    listed_before = project_policy_client.get(
        "/api/v1/projects", headers=user_headers
    ).json()["items"]
    assert project["id"] not in {item["id"] for item in listed_before}

    invitation = project_policy_client.post(
        f"{project_path}/members",
        headers=admin_headers,
        json={"email": user["email"]},
    )
    assert invitation.status_code == 201, invitation.text
    assert user["email"] in TOKENS
    assert project_policy_client.get(project_path, headers=user_headers).status_code == 403

    accepted = project_policy_client.post(
        "/api/v1/project-invitations/accept",
        headers=user_headers,
        json={"token": TOKENS[str(user["email"])]},
    )
    assert accepted.status_code == 200, accepted.text
    assert project_policy_client.get(project_path, headers=user_headers).status_code == 200
    listed_after = project_policy_client.get(
        "/api/v1/projects", headers=user_headers
    ).json()["items"]
    assert project["id"] in {item["id"] for item in listed_after}


@pytest.mark.database
def test_only_admin_can_delete_project(project_policy_client: TestClient) -> None:
    _, user_headers = create_verified_test_user(project_policy_client, "project-delete-denied")
    admin_headers = _admin_headers(project_policy_client)
    created = project_policy_client.post(
        "/api/v1/projects",
        headers=admin_headers,
        json={"name": "Delete Workspace", "key": f"delete-{uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    project_path = f"/api/v1/projects/{created.json()['id']}"

    denied = project_policy_client.delete(project_path, headers=user_headers)
    assert denied.status_code == 403
    assert denied.json()["code"] == "forbidden"

    deleted = project_policy_client.delete(project_path, headers=admin_headers)
    assert deleted.status_code == 204
    assert project_policy_client.get(project_path, headers=admin_headers).status_code == 404

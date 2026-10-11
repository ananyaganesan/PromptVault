"""Cross-cutting authorization and input-boundary checks."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.support import admin_headers, create_project, create_prompt, register


@pytest.mark.database
def test_anonymous_user_admin_and_object_scope_boundaries(api_client: TestClient) -> None:
    anonymous = api_client.get("/api/v1/projects")
    assert anonymous.status_code == 401

    _, owner_headers = register(api_client, "security-owner")
    _, outsider_headers = register(api_client, "security-outsider")
    project = create_project(api_client, owner_headers, label="Security")
    prompt = create_prompt(api_client, owner_headers, project["id"])

    denied_admin = api_client.get("/api/v1/admin/dashboard", headers=owner_headers)
    assert denied_admin.status_code == 403
    assert denied_admin.json()["code"] == "forbidden"

    hidden = api_client.get(f"/api/v1/prompts/{prompt['id']}", headers=outsider_headers)
    unknown = api_client.get(f"/api/v1/prompts/{uuid4()}", headers=outsider_headers)
    assert (hidden.status_code, hidden.json()["code"]) == (404, "not_found")
    assert (unknown.status_code, unknown.json()["code"]) == (404, "not_found")

    bad_filter = api_client.get(
        "/api/v1/projects", headers=owner_headers, params={"secret": "value"}
    )
    oversized_page = api_client.get(
        "/api/v1/projects", headers=owner_headers, params={"page_size": 101}
    )
    assert (bad_filter.status_code, bad_filter.json()["code"]) == (400, "invalid_filter")
    assert (oversized_page.status_code, oversized_page.json()["code"]) == (
        400,
        "invalid_filter",
    )


@pytest.mark.database
def test_registration_cannot_escalate_role_and_inactive_sessions_fail_closed(
    api_client: TestClient,
) -> None:
    escalated = api_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"escalation-{uuid4().hex}@example.com",
            "password": "CorrectHorse2026!",
            "display_name": "Escalation",
            "role": "admin",
        },
    )
    assert escalated.status_code == 422

    user, headers = register(api_client, "inactive-security")
    disabled = api_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers(api_client),
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    rejected = api_client.get("/api/v1/auth/me", headers=headers)
    assert (rejected.status_code, rejected.json()["code"]) == (401, "invalid_token")

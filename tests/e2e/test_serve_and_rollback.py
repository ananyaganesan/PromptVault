"""Runtime serving follows the active production deployment through rollback."""

import pytest
from fastapi.testclient import TestClient

from tests.support import (
    add_version,
    admin_headers,
    create_project,
    create_prompt,
    register,
)


@pytest.mark.database
def test_runtime_token_observes_auditable_rollback_and_revocation(
    api_client: TestClient,
) -> None:
    _, owner_headers = register(api_client, "serve-owner")
    administrator = admin_headers(api_client)
    project = create_project(api_client, owner_headers, label="Serve")
    prompt = create_prompt(api_client, owner_headers, project["id"])
    v1 = prompt["latest_version"]
    v2 = add_version(api_client, owner_headers, prompt["id"], v1["id"], 2)
    v3 = add_version(api_client, owner_headers, prompt["id"], v2["id"], 3)

    pending = api_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": v3["id"], "environment": "prod"},
    ).json()
    assert api_client.post(
        f"/api/v1/admin/deployments/{pending['id']}/approve",
        headers=administrator,
        json={},
    ).status_code == 200

    token_response = api_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={"project_id": project["id"], "name": "Runtime"},
    )
    assert token_response.status_code == 201
    issued = token_response.json()
    runtime_headers = {"Authorization": f"Bearer {issued['token']}"}
    before = api_client.get(
        "/serve/v1/prompts/support-reply", headers=runtime_headers, params={"env": "prod"}
    )
    assert before.status_code == 200
    assert before.json()["version"]["id"] == v3["id"]

    rollback = api_client.post(
        f"/api/v1/admin/prompts/{prompt['id']}/rollback",
        headers=administrator,
        json={"target_version_id": v2["id"], "reason": "v3 regression"},
    )
    assert rollback.status_code == 201
    assert rollback.json()["rollback_of_id"] == pending["id"]
    after = api_client.get("/serve/v1/prompts/support-reply", headers=runtime_headers)
    assert after.status_code == 200
    assert after.json()["version"]["id"] == v2["id"]

    assert api_client.delete(
        f"/api/v1/api-tokens/{issued['id']}", headers=owner_headers
    ).status_code == 204
    revoked = api_client.get("/serve/v1/prompts/support-reply", headers=runtime_headers)
    assert (revoked.status_code, revoked.json()["code"]) == (401, "invalid_token")

    deployment_audit = api_client.get(
        "/api/v1/admin/audit",
        headers=administrator,
        params={"entity_type": "deployments", "entity_id": pending["id"]},
    )
    rollback_audit = api_client.get(
        "/api/v1/admin/audit",
        headers=administrator,
        params={"entity_type": "deployments", "entity_id": rollback.json()["id"]},
    )
    token_audit = api_client.get(
        "/api/v1/admin/audit",
        headers=administrator,
        params={"entity_type": "api_tokens", "entity_id": issued["id"]},
    )
    assert deployment_audit.status_code == rollback_audit.status_code == 200
    assert token_audit.status_code == 200
    assert {item["action"] for item in deployment_audit.json()["items"]} == {
        "insert",
        "update",
    }
    assert {item["action"] for item in rollback_audit.json()["items"]} == {"insert"}
    assert {item["action"] for item in token_audit.json()["items"]} == {
        "insert",
        "update",
    }

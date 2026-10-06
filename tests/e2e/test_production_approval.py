"""Production activation is an admin-reviewed, conflict-safe workflow."""

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
def test_staging_then_production_approval_with_forbidden_and_conflict_evidence(
    api_client: TestClient,
) -> None:
    _, owner_headers = register(api_client, "approval-owner")
    project = create_project(api_client, owner_headers, label="Approval")
    prompt = create_prompt(api_client, owner_headers, project["id"])
    version_one = prompt["latest_version"]
    version = add_version(
        api_client, owner_headers, prompt["id"], version_one["id"], 2
    )
    administrator = admin_headers(api_client)

    initial_production = api_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version_one["id"], "environment": "prod"},
    ).json()
    assert api_client.post(
        f"/api/v1/admin/deployments/{initial_production['id']}/approve",
        headers=administrator,
        json={"review_note": "baseline"},
    ).status_code == 200

    staging = api_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "staging"},
    )
    assert (staging.status_code, staging.json()["status"]) == (201, "active")
    evidence = api_client.post(
        "/api/v1/runs",
        headers=owner_headers,
        json={
            "version_id": version["id"],
            "variables": {"name": "Jobin", "order_id": "42"},
        },
    )
    assert evidence.status_code == 201

    requested = api_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    )
    assert (requested.status_code, requested.json()["status"]) == (201, "pending")
    deployment_id = requested.json()["id"]

    forbidden = api_client.post(
        f"/api/v1/admin/deployments/{deployment_id}/approve",
        headers=owner_headers,
        json={"review_note": "self approval"},
    )
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "forbidden")

    detail = api_client.get(
        f"/api/v1/admin/deployments/{deployment_id}", headers=administrator
    )
    assert detail.status_code == 200
    assert detail.json()["requested_version"]["id"] == version["id"]
    assert detail.json()["active_version"]["id"] == version_one["id"]
    assert evidence.json()["id"] in {
        run["id"] for run in detail.json()["recent_runs"]
    }

    approved = api_client.post(
        f"/api/v1/admin/deployments/{deployment_id}/approve",
        headers=administrator,
        json={"review_note": "evidence reviewed"},
    )
    assert (approved.status_code, approved.json()["status"]) == (200, "active")
    repeated = api_client.post(
        f"/api/v1/admin/deployments/{deployment_id}/reject",
        headers=administrator,
        json={"review_note": "too late"},
    )
    assert (repeated.status_code, repeated.json()["code"]) == (409, "already_reviewed")

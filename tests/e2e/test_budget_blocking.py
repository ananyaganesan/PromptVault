"""Budget changes atomically block and later permit provider execution."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.support import admin_headers, create_project, create_prompt, register


@pytest.mark.database
def test_budget_changes_preserve_zero_cost_gemini_execution(
    api_client: TestClient,
) -> None:
    user, owner_headers = register(api_client, "budget-story-owner")
    administrator = admin_headers(api_client)
    project = create_project(api_client, owner_headers, label="Budget")
    version = create_prompt(api_client, owner_headers, project["id"])["latest_version"]

    budget_response = api_client.post(
        "/api/v1/admin/budgets",
        headers=administrator,
        json={"project_id": project["id"], "monthly_limit": "0", "timezone": "UTC"},
    )
    assert budget_response.status_code == 201
    budget = budget_response.json()

    payload = {
        "version_id": version["id"],
        "variables": {"name": "Jobin", "order_id": "42"},
    }
    blocked = api_client.post("/api/v1/runs", headers=owner_headers, json=payload)
    assert blocked.status_code == 201
    assert blocked.json()["status"] == "completed"
    assert Decimal(blocked.json()["cost"]) == 0

    raised = api_client.patch(
        f"/api/v1/admin/budgets/{budget['id']}",
        headers=administrator,
        json={"monthly_limit": "10.000000"},
    )
    assert raised.status_code == 200
    completed = api_client.post("/api/v1/runs", headers=owner_headers, json=payload)
    assert completed.status_code == 201
    assert completed.json()["status"] == "completed"

    dashboard = api_client.get("/api/v1/dashboard/me", headers=owner_headers)
    organization = api_client.get("/api/v1/admin/dashboard", headers=administrator)
    audit = api_client.get(
        "/api/v1/admin/audit",
        headers=administrator,
        params={"entity_type": "budgets", "entity_id": budget["id"]},
    )
    assert dashboard.status_code == organization.status_code == audit.status_code == 200
    assert dashboard.json()["blocked_run_count"] == 0
    assert dashboard.json()["completed_run_count"] == 2
    assert Decimal(dashboard.json()["monthly_spend"]) == 0
    assert audit.json()["total"] == 2
    assert user["id"] == completed.json()["user_id"]

"""The main user workflow crosses auth, projects, versioning, runs, and dashboard."""

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from tests.invitation_support import accept_invitation
from tests.support import add_version, create_project, create_prompt, register


@pytest.mark.database
def test_user_can_build_version_and_execute_a_prompt(api_client: TestClient) -> None:
    _, owner_headers = register(api_client, "story-owner")
    member, member_headers = register(api_client, "story-member")
    project = create_project(api_client, owner_headers)
    added = api_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert added.status_code == 201
    accept_invitation(api_client, str(member["email"]), member_headers)

    prompt = create_prompt(api_client, owner_headers, project["id"])
    v1 = prompt["latest_version"]
    v2 = add_version(api_client, member_headers, prompt["id"], v1["id"], 2)
    v3 = add_version(api_client, owner_headers, prompt["id"], v2["id"], 3)

    history = api_client.get(
        f"/api/v1/prompts/{prompt['id']}/versions", headers=member_headers
    )
    diff = api_client.get(
        f"/api/v1/versions/{v3['id']}/diff",
        headers=member_headers,
        params={"against": v2["id"]},
    )
    lineage = api_client.get(f"/api/v1/versions/{v3['id']}/lineage", headers=member_headers)
    assert [item["version_number"] for item in history.json()["items"]] == [3, 2, 1]
    assert diff.status_code == 200
    assert [item["version_number"] for item in lineage.json()["items"]] == [3, 2, 1]

    executed = api_client.post(
        "/api/v1/runs",
        headers=member_headers,
        json={"version_id": v3["id"], "variables": {"name": "Jobin", "order_id": "42"}},
    )
    assert executed.status_code == 201, executed.text
    run = executed.json()
    assert run["status"] == "completed"
    assert run["prompt_tokens"] > 0 and run["completion_tokens"] > 0
    assert run["latency_ms"] >= 0 and Decimal(run["cost"]) >= 0

    dashboard = api_client.get("/api/v1/dashboard/me", headers=member_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["completed_run_count"] == 1


@pytest.mark.database
def test_application_pool_restart_preserves_committed_state(
    isolated_database_url: str,
) -> None:
    os.environ.setdefault("DATABASE_URL", isolated_database_url)
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("SECRET_KEY", "test-secret-that-is-at-least-32-characters")
    from api.app.main import create_app

    settings = Settings(
        environment="test",
        database_url=isolated_database_url,
        secret_key="test-secret-that-is-at-least-32-characters",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as first_process:
        _, headers = register(first_process, "restart-owner")
        project = create_project(first_process, headers, label=f"Restart-{uuid4().hex[:8]}")
        assert first_process.get("/ready").status_code == 200

    with TestClient(create_app(settings)) as restarted_process:
        persisted = restarted_process.get(
            f"/api/v1/projects/{project['id']}", headers=headers
        )
        assert restarted_process.get("/ready").status_code == 200
        assert persisted.status_code == 200
        assert persisted.json()["id"] == project["id"]

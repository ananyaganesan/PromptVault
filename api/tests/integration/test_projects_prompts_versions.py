from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from tests.auth_support import create_verified_test_user


@pytest.fixture(scope="module")
def domain_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def register_user(client: TestClient, label: str) -> tuple[dict[str, object], dict[str, str]]:
    return create_verified_test_user(client, label)


def create_project(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    key = f"project-{uuid4().hex}"
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Support Workspace", "key": key, "description": "Initial"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.database
def test_project_membership_is_scoped_and_owner_controls_mutations(
    domain_client: TestClient,
) -> None:
    owner, owner_headers = register_user(domain_client, "project-owner")
    member, member_headers = register_user(domain_client, "project-member")
    _, outsider_headers = register_user(domain_client, "project-outsider")

    project = create_project(domain_client, owner_headers)
    project_id = project["id"]
    assert project["owner"]["id"] == owner["id"]
    assert project["member_count"] == 1
    assert project["prompt_count"] == 0

    owner_page = domain_client.get("/api/v1/projects", headers=owner_headers)
    outsider_page = domain_client.get("/api/v1/projects", headers=outsider_headers)
    assert owner_page.status_code == 200
    assert project_id in {item["id"] for item in owner_page.json()["items"]}
    assert project_id not in {item["id"] for item in outsider_page.json()["items"]}

    hidden = domain_client.get(f"/api/v1/projects/{project_id}", headers=outsider_headers)
    unknown = domain_client.get(f"/api/v1/projects/{uuid4()}", headers=outsider_headers)
    assert hidden.status_code == 403
    assert unknown.status_code == 403
    assert hidden.json()["code"] == "forbidden"

    added = domain_client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert added.status_code == 201
    assert added.json()["id"] == member["id"]
    assert added.json()["is_owner"] is False

    duplicate = domain_client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"

    missing_user = domain_client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner_headers,
        json={"email": f"missing-{uuid4()}@example.com"},
    )
    assert missing_user.status_code == 404

    members = domain_client.get(
        f"/api/v1/projects/{project_id}/members",
        headers=member_headers,
    )
    assert members.status_code == 200
    assert members.json()["total"] == 2

    forbidden_patch = domain_client.patch(
        f"/api/v1/projects/{project_id}",
        headers=member_headers,
        json={"name": "Member Rename"},
    )
    assert forbidden_patch.status_code == 403

    updated = domain_client.patch(
        f"/api/v1/projects/{project_id}",
        headers=owner_headers,
        json={"name": "Renamed Workspace", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Workspace"
    assert updated.json()["description"] is None

    owner_removal = domain_client.delete(
        f"/api/v1/projects/{project_id}/members/{owner['id']}",
        headers=owner_headers,
    )
    assert owner_removal.status_code == 409

    removed = domain_client.delete(
        f"/api/v1/projects/{project_id}/members/{member['id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 204
    missing_removal = domain_client.delete(
        f"/api/v1/projects/{project_id}/members/{uuid4()}",
        headers=owner_headers,
    )
    assert missing_removal.status_code == 404
    denied_after_removal = domain_client.get(
        f"/api/v1/projects/{project_id}",
        headers=member_headers,
    )
    assert denied_after_removal.status_code == 403


@pytest.mark.database
def test_prompt_versions_are_immutable_snapshots_with_diff_and_lineage(
    domain_client: TestClient,
) -> None:
    _, owner_headers = register_user(domain_client, "prompt-owner")
    _, outsider_headers = register_user(domain_client, "prompt-outsider")
    project = create_project(domain_client, owner_headers)
    project_id = project["id"]

    created = domain_client.post(
        f"/api/v1/projects/{project_id}/prompts",
        headers=owner_headers,
        json={
            "key": "support-reply",
            "name": "Support Reply",
            "description": "Initial metadata",
            "template_body": (
                "Reply to {{customer_message}} for {{order_id}} and {{customer_message}}."
            ),
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 500,
            },
            "commit_message": "Initial version",
        },
    )
    assert created.status_code == 201
    prompt = created.json()
    prompt_id = prompt["id"]
    version_one = prompt["latest_version"]
    assert version_one["version_number"] == 1
    assert version_one["parent_version_id"] is None
    assert version_one["variables"] == ["customer_message", "order_id"]

    second = domain_client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=owner_headers,
        json={
            "parent_version_id": version_one["id"],
            "template_body": "Order {{order_id}} question: {{customer_message}} ({{locale}})",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v2",
                "temperature": 0.2,
                "max_output_tokens": 700,
            },
            "commit_message": "Add locale and new model",
        },
    )
    assert second.status_code == 201
    version_two = second.json()
    assert version_two["version_number"] == 2
    assert version_two["variables"] == ["order_id", "customer_message", "locale"]

    history = domain_client.get(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=owner_headers,
    )
    assert history.status_code == 200
    assert [item["version_number"] for item in history.json()["items"]] == [2, 1]

    detail = domain_client.get(
        f"/api/v1/versions/{version_one['id']}",
        headers=owner_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["template_body"] == version_one["template_body"]

    diff = domain_client.get(
        f"/api/v1/versions/{version_two['id']}/diff",
        params={"against": version_one["id"]},
        headers=owner_headers,
    )
    assert diff.status_code == 200
    assert diff.json()["from_version_id"] == version_one["id"]
    assert diff.json()["to_version_id"] == version_two["id"]
    assert diff.json()["variables"] == {"added": ["locale"], "removed": []}
    assert diff.json()["model_config"]["changed_fields"] == [
        "max_output_tokens",
        "model",
        "temperature",
    ]

    lineage = domain_client.get(
        f"/api/v1/versions/{version_two['id']}/lineage",
        headers=owner_headers,
    )
    assert lineage.status_code == 200
    assert [item["version_number"] for item in lineage.json()["items"]] == [2, 1]
    assert lineage.json()["cycle_detected"] is False

    metadata = domain_client.patch(
        f"/api/v1/prompts/{prompt_id}",
        headers=owner_headers,
        json={"name": "Renamed Prompt", "description": None},
    )
    assert metadata.status_code == 200
    assert metadata.json()["name"] == "Renamed Prompt"
    assert metadata.json()["latest_version"]["id"] == version_two["id"]

    bad_parent = domain_client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=owner_headers,
        json={
            "parent_version_id": str(uuid4()),
            "template_body": "Still {{valid}}",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Wrong parent",
        },
    )
    assert bad_parent.status_code == 409
    assert bad_parent.json()["code"] == "conflict"

    prompt_page = domain_client.get(
        f"/api/v1/projects/{project_id}/prompts",
        headers=owner_headers,
    )
    assert prompt_page.status_code == 200
    assert prompt_page.json()["items"][0]["latest_version_number"] == 2

    hidden = domain_client.get(f"/api/v1/prompts/{prompt_id}", headers=outsider_headers)
    hidden_version = domain_client.get(
        f"/api/v1/versions/{version_two['id']}",
        headers=outsider_headers,
    )
    unknown_prompt = domain_client.get(f"/api/v1/prompts/{uuid4()}", headers=outsider_headers)
    unknown_version = domain_client.get(
        f"/api/v1/versions/{uuid4()}",
        headers=outsider_headers,
    )
    assert hidden.status_code == unknown_prompt.status_code == 404
    assert hidden_version.status_code == unknown_version.status_code == 404


@pytest.mark.database
def test_duplicate_project_and_prompt_keys_return_stable_conflicts(
    domain_client: TestClient,
) -> None:
    _, headers = register_user(domain_client, "duplicate-owner")
    project = create_project(domain_client, headers)

    duplicate_project = domain_client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Duplicate", "key": project["key"]},
    )
    assert duplicate_project.status_code == 409
    assert duplicate_project.json()["code"] == "duplicate_key"

    payload = {
        "key": "same-key",
        "name": "First prompt",
        "template_body": "Hello {{name}}",
        "model_config": {
            "provider": "mock",
            "model": "deterministic-v1",
            "temperature": 0,
            "max_output_tokens": 100,
        },
        "commit_message": "Initial",
    }
    first = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 201
    duplicate_prompt = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={**payload, "name": "Duplicate prompt"},
    )
    assert duplicate_prompt.status_code == 409
    assert duplicate_prompt.json()["code"] == "duplicate_key"


@pytest.mark.database
@pytest.mark.parametrize(
    "query",
    [
        {"page": "0"},
        {"page_size": "101"},
        {"sort": "unsupported"},
        {"direction": "sideways"},
        {"unsupported": "value"},
    ],
)
def test_invalid_list_filters_use_the_stable_invalid_filter_error(
    domain_client: TestClient,
    query: dict[str, str],
) -> None:
    _, headers = register_user(domain_client, "invalid-filter")

    response = domain_client.get("/api/v1/projects", params=query, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_filter"


@pytest.mark.database
def test_project_member_can_create_and_update_prompt_but_anonymous_user_cannot(
    domain_client: TestClient,
) -> None:
    _, owner_headers = register_user(domain_client, "member-flow-owner")
    member, member_headers = register_user(domain_client, "member-flow-user")
    project = create_project(domain_client, owner_headers)
    added = domain_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert added.status_code == 201

    created = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=member_headers,
        json={
            "key": "member-prompt",
            "name": "Member Prompt",
            "template_body": "Hello {{name}}",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Created by member",
        },
    )
    assert created.status_code == 201

    updated = domain_client.patch(
        f"/api/v1/prompts/{created.json()['id']}",
        headers=member_headers,
        json={"name": "Member Updated Prompt"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Member Updated Prompt"

    removed = domain_client.delete(
        f"/api/v1/projects/{project['id']}/members/{member['id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 204
    denied_update = domain_client.patch(
        f"/api/v1/prompts/{created.json()['id']}",
        headers=member_headers,
        json={"name": "Must Not Change"},
    )
    denied_version = domain_client.post(
        f"/api/v1/prompts/{created.json()['id']}/versions",
        headers=member_headers,
        json={
            "parent_version_id": created.json()["latest_version"]["id"],
            "template_body": "Denied {{name}}",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Denied",
        },
    )
    assert denied_update.status_code == 404
    assert denied_version.status_code == 404

    anonymous = domain_client.get(f"/api/v1/projects/{project['id']}")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"


@pytest.mark.database
def test_invalid_template_rolls_back_prompt_and_cross_prompt_diff_is_rejected(
    domain_client: TestClient,
) -> None:
    _, headers = register_user(domain_client, "rollback-owner")
    project = create_project(domain_client, headers)
    model_config = {
        "provider": "mock",
        "model": "deterministic-v1",
        "temperature": 0,
        "max_output_tokens": 100,
    }
    invalid = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "atomic-prompt",
            "name": "Atomic Prompt",
            "template_body": "Hello {{not-valid}}",
            "model_config": model_config,
            "commit_message": "Invalid",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"

    first = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "atomic-prompt",
            "name": "Atomic Prompt",
            "template_body": "Hello {{valid_name}}",
            "model_config": model_config,
            "commit_message": "Valid after rollback",
        },
    )
    second = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "other-prompt",
            "name": "Other Prompt",
            "template_body": "Other {{valid_name}}",
            "model_config": model_config,
            "commit_message": "Other initial",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    cross_prompt = domain_client.get(
        f"/api/v1/versions/{first.json()['latest_version']['id']}/diff",
        params={"against": second.json()["latest_version"]["id"]},
        headers=headers,
    )
    assert cross_prompt.status_code == 409
    assert cross_prompt.json()["code"] == "conflict"


@pytest.mark.database
def test_project_writes_record_actor_and_request_id(
    domain_client: TestClient,
    seeded_database_url: str,
) -> None:
    actor, headers = register_user(domain_client, "audit-owner")
    headers["X-Request-ID"] = "project-audit-test"

    project = create_project(domain_client, headers)

    with psycopg.connect(seeded_database_url, row_factory=dict_row) as connection:
        event = connection.execute(
            """
            SELECT actor_user_id, request_id
            FROM audit_events
            WHERE entity_type = 'projects' AND entity_id = %s AND action = 'insert'
            """,
            (project["id"],),
        ).fetchone()
    assert event is not None
    assert str(event["actor_user_id"]) == actor["id"]
    assert event["request_id"] == "project-audit-test"


@pytest.mark.database
def test_admin_prompt_routes_return_not_found_for_unknown_project(
    domain_client: TestClient,
) -> None:
    login = domain_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = domain_client.get(
        f"/api/v1/projects/{uuid4()}/prompts",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.database
def test_admin_can_use_project_prompt_and_version_routes(
    domain_client: TestClient,
) -> None:
    _, owner_headers = register_user(domain_client, "admin-scope-owner")
    project = create_project(domain_client, owner_headers)
    prompt = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=owner_headers,
        json={
            "key": "admin-visible",
            "name": "Admin Visible",
            "template_body": "Hello {{name}}",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Initial",
        },
    ).json()
    login = domain_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    project_detail = domain_client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    project_update = domain_client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={"name": "Admin Renamed"},
    )
    prompt_detail = domain_client.get(f"/api/v1/prompts/{prompt['id']}", headers=headers)
    version_detail = domain_client.get(
        f"/api/v1/versions/{prompt['latest_version']['id']}",
        headers=headers,
    )
    unknown_project = domain_client.get(f"/api/v1/projects/{uuid4()}", headers=headers)

    assert project_detail.status_code == 200
    assert project_update.status_code == 200
    assert prompt_detail.status_code == 200
    assert version_detail.status_code == 200
    assert unknown_project.status_code == 404


@pytest.mark.database
def test_lineage_detects_a_corrupt_cycle_without_looping(
    domain_client: TestClient,
    seeded_database_url: str,
) -> None:
    _, headers = register_user(domain_client, "cycle-owner")
    project = create_project(domain_client, headers)
    first = domain_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "cycle-test",
            "name": "Cycle Test",
            "template_body": "First",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "First",
        },
    ).json()["latest_version"]
    second = domain_client.post(
        f"/api/v1/prompts/{first['prompt_id']}/versions",
        headers=headers,
        json={
            "parent_version_id": first["id"],
            "template_body": "Second",
            "model_config": first["model_config"],
            "commit_message": "Second",
        },
    ).json()

    with psycopg.connect(seeded_database_url, autocommit=True) as connection:
        try:
            connection.execute("SET session_replication_role = replica")
            connection.execute(
                "UPDATE prompt_versions SET parent_version_id = %s WHERE id = %s",
                (second["id"], first["id"]),
            )
        finally:
            connection.execute("SET session_replication_role = origin")

    lineage = domain_client.get(
        f"/api/v1/versions/{second['id']}/lineage",
        headers=headers,
    )
    assert lineage.status_code == 200
    assert [item["version_number"] for item in lineage.json()["items"]] == [2, 1]
    assert lineage.json()["cycle_detected"] is True


@pytest.mark.database
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/projects", None),
        ("post", "/api/v1/projects", {"name": "X", "key": "anonymous"}),
        ("get", f"/api/v1/projects/{uuid4()}", None),
        ("patch", f"/api/v1/projects/{uuid4()}", {"name": "X"}),
        ("get", f"/api/v1/projects/{uuid4()}/members", None),
        (
            "post",
            f"/api/v1/projects/{uuid4()}/members",
            {"email": "member@example.com"},
        ),
        ("delete", f"/api/v1/projects/{uuid4()}/members/{uuid4()}", None),
        (
            "post",
            f"/api/v1/projects/{uuid4()}/prompts",
            {
                "key": "anonymous-prompt",
                "name": "Anonymous",
                "template_body": "Hello",
                "model_config": {
                    "provider": "mock",
                    "model": "deterministic-v1",
                    "temperature": 0,
                    "max_output_tokens": 100,
                },
                "commit_message": "Anonymous",
            },
        ),
        ("get", f"/api/v1/prompts/{uuid4()}", None),
        ("patch", f"/api/v1/prompts/{uuid4()}", {"name": "X"}),
        (
            "post",
            f"/api/v1/prompts/{uuid4()}/versions",
            {
                "parent_version_id": str(uuid4()),
                "template_body": "Hello",
                "model_config": {
                    "provider": "mock",
                    "model": "deterministic-v1",
                    "temperature": 0,
                    "max_output_tokens": 100,
                },
                "commit_message": "Anonymous",
            },
        ),
        ("get", f"/api/v1/prompts/{uuid4()}/versions", None),
        ("get", f"/api/v1/versions/{uuid4()}", None),
        ("get", f"/api/v1/versions/{uuid4()}/diff?against={uuid4()}", None),
        ("get", f"/api/v1/versions/{uuid4()}/lineage", None),
    ],
)
def test_phase_two_routes_reject_anonymous_requests(
    domain_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    response = domain_client.request(method, path, json=payload)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"

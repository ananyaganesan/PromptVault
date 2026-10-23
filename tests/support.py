"""Small public-API helpers shared by stabilization tests."""

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.auth_support import create_verified_test_user, seed_owned_project


def register(
    client: TestClient, label: str
) -> tuple[dict[str, object], dict[str, str]]:
    return create_verified_test_user(client, label)


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_project(
    client: TestClient, headers: dict[str, str], *, label: str = "Story"
) -> dict[str, object]:
    response = seed_owned_project(
        client,
        headers,
        {"name": f"{label} Project", "key": f"{label.lower()}-{uuid4().hex}"},
    )
    return response


def create_prompt(
    client: TestClient,
    headers: dict[str, str],
    project_id: object,
    *,
    key: str = "support-reply",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "key": key,
            "name": "Support Reply",
            "template_body": "Hello {{name}}, order {{order_id}} is ready.",
            "model_config": {
                "provider": "gemini",
                "model": "gemini-3.5-flash-lite",
                "temperature": 0,
                "max_output_tokens": 200,
            },
            "commit_message": "Initial prompt",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_version(
    client: TestClient,
    headers: dict[str, str],
    prompt_id: object,
    parent_id: object,
    number: int,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "parent_version_id": parent_id,
            "template_body": f"Version {number}: {{{{name}}}} / {{{{order_id}}}}.",
            "model_config": {
                "provider": "gemini",
                "model": "gemini-3.5-flash-lite",
                "temperature": 0,
                "max_output_tokens": 200,
            },
            "commit_message": f"Version {number}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()

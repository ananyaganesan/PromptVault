import pytest
from fastapi.testclient import TestClient

from tests.support import create_project, create_prompt, register


@pytest.mark.database
def test_production_rejects_mock_creation_versioning_and_execution(api_client: TestClient) -> None:
    _, headers = register(api_client, "provider-policy")
    project = create_project(api_client, headers)
    prompt = create_prompt(api_client, headers, project["id"])
    version = prompt["latest_version"]
    settings = api_client.app.state.settings
    api_client.app.state.settings = settings.model_copy(update={"environment": "production"})
    try:
        attempts = [
            (f"/api/v1/projects/{project['id']}/prompts", {
                "name": "Denied mock", "key": "denied-mock", "template_body": "Hello",
                "model_config": version["model_config"], "commit_message": "Initial",
            }),
            (f"/api/v1/prompts/{prompt['id']}/versions", {
                "parent_version_id": version["id"], "template_body": "Hello",
                "model_config": version["model_config"], "commit_message": "Denied mock",
            }),
            ("/api/v1/runs", {
                "version_id": version["id"], "variables": {"name": "User", "order_id": "1"},
            }),
        ]
        for path, payload in attempts:
            response = api_client.post(path, headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["code"] == "validation_error"
    finally:
        api_client.app.state.settings = settings
    assert api_client.get(
        f"/api/v1/prompts/{prompt['id']}/versions", headers=headers,
    ).json()["total"] == 1
    assert api_client.get("/api/v1/runs", headers=headers).json()["total"] == 0

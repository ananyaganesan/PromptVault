"""The current Gemini-only policy is enforced in every environment."""

import pytest
from fastapi.testclient import TestClient

from tests.support import admin_headers, create_project, create_prompt, register


@pytest.mark.database
@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize("provider", ["mock", "openrouter", "groq"])
def test_removed_providers_are_rejected_in_every_environment(
    api_client: TestClient, environment: str, provider: str
) -> None:
    _, headers = register(api_client, "provider-policy")
    project = create_project(api_client, headers)
    prompt = create_prompt(api_client, headers, project["id"])
    version = prompt["latest_version"]
    admin = admin_headers(api_client)
    settings = api_client.app.state.settings
    api_client.app.state.settings = settings.model_copy(
        update={"environment": environment}
    )
    try:
        discovery = api_client.get("/api/v1/providers/models", headers=headers)
        assert discovery.status_code == 200
        assert [row["provider"] for row in discovery.json()["items"]] == ["gemini"]
        assert "internal_mock_allowed" not in discovery.json()
        config = version["model_config"] | {"provider": provider}
        for path, payload in [
            (
                f"/api/v1/projects/{project['id']}/prompts",
                {
                    "name": "Denied",
                    "key": "denied",
                    "template_body": "Hello",
                    "model_config": config,
                    "commit_message": "Denied",
                },
            ),
            (
                f"/api/v1/prompts/{prompt['id']}/versions",
                {
                    "parent_version_id": version["id"],
                    "template_body": "Hello",
                    "model_config": config,
                    "commit_message": "Denied",
                },
            ),
            (
                "/api/v1/admin/provider-keys",
                {"provider": provider, "alias": "denied", "secret": "not-a-real-key"},
            ),
            (
                "/api/v1/admin/model-pricing",
                {
                    "provider": provider,
                    "model": "anything",
                    "input_price_per_million": 0,
                    "output_price_per_million": 0,
                    "effective_from": "2026-01-01T00:00:00Z",
                },
            ),
        ]:
            response = api_client.post(
                path, headers=admin if "/admin/" in path else headers, json=payload
            )
            assert response.status_code == 422, (path, response.text)
    finally:
        api_client.app.state.settings = settings
    assert (
        api_client.get(
            f"/api/v1/prompts/{prompt['id']}/versions", headers=headers
        ).json()["total"]
        == 1
    )

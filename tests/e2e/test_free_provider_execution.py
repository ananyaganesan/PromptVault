"""Full local API/SQL flows with simulated provider HTTP, never paid calls."""

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.support import admin_headers, create_project, register

MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "openrouter": "liquid/lfm-2.5-2.6b:free",
    "groq": "qwen/qwen3.8-27b",
}


def configure(
    client: TestClient, provider: str
) -> tuple[dict[str, str], dict[str, object]]:
    _, headers = register(client, "free-provider-owner")
    project = create_project(client, headers)
    admin = admin_headers(client)
    assert (
        client.post(
            "/api/v1/admin/provider-keys",
            headers=admin,
            json={
                "provider": provider,
                "alias": "free-project",
                "secret": "private-project-key",
            },
        ).status_code
        == 201
    )
    response = client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "free-text",
            "name": "Free text",
            "template_body": "Hello {{name}}",
            "model_config": {
                "provider": provider,
                "model": MODELS[provider],
                "max_output_tokens": 100,
            },
            "commit_message": "Initial",
        },
    )
    assert response.status_code == 201
    return headers, response.json()["latest_version"]


@pytest.mark.database
@pytest.mark.parametrize("provider", ["gemini", "openrouter", "groq"])
def test_free_execution_is_persisted_and_duplicate_does_not_call_again(
    api_client: TestClient,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    headers, version = configure(api_client, provider)
    discovery = api_client.get("/api/v1/providers/models", headers=headers)
    assert discovery.status_code == 200
    assert [item["provider"] for item in discovery.json()["items"]] == [
        "gemini",
        "openrouter",
        "groq",
    ]
    selected = next(
        item for item in discovery.json()["items"] if item["provider"] == provider
    )
    assert selected["credential_available"] is True
    assert all(model["available"] for model in selected["models"])
    assert (
        "private-project-key" not in discovery.text
        and "encrypted_secret" not in discovery.text
    )
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if provider == "gemini":
            payload = {
                "candidates": [{"content": {"parts": [{"text": "Provider output"}]}}],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
            }
        else:
            payload = {
                "choices": [{"message": {"content": "Provider output"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            }
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handle)),
    )
    headers = {**headers, "Idempotency-Key": "free-provider-request-0001"}
    payload = {"version_id": version["id"], "variables": {"name": "User"}}
    first = api_client.post("/api/v1/runs", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    replay = api_client.post("/api/v1/runs", headers=headers, json=payload)
    assert replay.status_code == 201 and first.json()["id"] == replay.json()["id"]
    assert len(calls) == 1
    result = first.json()
    assert result["provider"] == provider and result["model"] == MODELS[provider]
    assert result["cost"] == "0.000000"
    assert result["prompt_tokens"] == 7 and result["completion_tokens"] == 3
    assert (
        api_client.get(f"/api/v1/runs/{result['id']}", headers=headers).json() == result
    )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT output_text, prompt_tokens, completion_tokens, cost FROM runs WHERE id=%s",
            (result["id"],),
        ).fetchone() == ("Provider output", 7, 3, 0)


@pytest.mark.database
@pytest.mark.parametrize(
    "status,code",
    [(429, "provider_quota_exceeded"), (401, "provider_configuration_error")],
)
def test_quota_and_bad_credentials_are_safe_and_recorded(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: str,
) -> None:
    headers, version = configure(api_client, "groq")
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="private-project-key"),
            )
        ),
    )
    response = api_client.post(
        "/api/v1/runs",
        headers=headers,
        json={"version_id": version["id"], "variables": {"name": "User"}},
    )
    assert response.status_code == (429 if status == 429 else 503)
    assert (
        response.json()["code"] == code and "private-project-key" not in response.text
    )
    rows = api_client.get("/api/v1/runs", headers=headers).json()["items"]
    assert (
        len(rows) == 1
        and rows[0]["status"] == "failed"
        and rows[0]["error_code"] == code
    )


@pytest.mark.database
def test_discovery_requires_authentication(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/providers/models").status_code == 401


@pytest.mark.database
def test_input_limits_and_missing_key_prevent_provider_call(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, version = configure(api_client, "groq")

    def unexpected_call(*args: object, **kwargs: object) -> None:
        pytest.fail("Provider must not be contacted for denied admission")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_call)
    response = api_client.post(
        "/api/v1/runs",
        headers=headers,
        json={
            "version_id": version["id"],
            "variables": {"name": "x" * 12001},
        },
    )
    assert response.status_code == 422
    admin = admin_headers(api_client)
    keys = api_client.get("/api/v1/admin/provider-keys", headers=admin).json()["items"]
    groq_key = next(key for key in keys if key["provider"] == "groq")
    assert (
        api_client.delete(
            f"/api/v1/admin/provider-keys/{groq_key['id']}", headers=admin
        ).status_code
        == 204
    )
    response = api_client.post(
        "/api/v1/runs",
        headers=headers,
        json={
            "version_id": version["id"],
            "variables": {"name": "User"},
        },
    )
    assert (
        response.status_code == 409
        and response.json()["code"] == "provider_not_configured"
    )
    discovery = api_client.get("/api/v1/providers/models", headers=headers).json()
    assert (
        next(item for item in discovery["items"] if item["provider"] == "groq")[
            "credential_available"
        ]
        is False
    )
    assert api_client.get("/api/v1/runs", headers=headers).json()["total"] == 0


@pytest.mark.database
def test_unsupported_model_cannot_be_saved(api_client: TestClient) -> None:
    headers, version = configure(api_client, "openrouter")
    response = api_client.post(
        f"/api/v1/prompts/{version['prompt_id']}/versions",
        headers=headers,
        json={
            "parent_version_id": version["id"],
            "template_body": "Hello",
            "model_config": {
                "provider": "openrouter",
                "model": "paid/model",
                "max_output_tokens": 100,
            },
            "commit_message": "Attempt paid model",
        },
    )
    assert (
        response.status_code == 409 and response.json()["code"] == "model_not_available"
    )

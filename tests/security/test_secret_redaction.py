"""Secrets must never appear in public responses, metadata, or structured logs."""

import json
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app.logging_config import JsonFormatter
from tests.support import admin_headers, create_project, register


def test_structured_formatter_ignores_unapproved_secret_fields() -> None:
    record = logging.LogRecord(
        "promptvault.request", logging.INFO, __file__, 1, "request_completed", (), None
    )
    record.request_id = "request-1"
    record.password = "NeverLogPassword!"
    record.authorization = "Bearer never-log-token"
    payload = JsonFormatter().format(record)

    assert json.loads(payload)["request_id"] == "request-1"
    assert "NeverLogPassword!" not in payload
    assert "never-log-token" not in payload


@pytest.mark.database
def test_runtime_and_provider_secrets_are_write_only(
    api_client: TestClient, database_url: str
) -> None:
    _, owner_headers = register(api_client, "redaction-owner")
    project = create_project(api_client, owner_headers, label="Redaction")
    created_token = api_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={"project_id": project["id"], "name": "production"},
    )
    assert created_token.status_code == 201
    plaintext = created_token.json()["token"]

    listed = api_client.get(
        "/api/v1/api-tokens", headers=owner_headers, params={"project_id": project["id"]}
    )
    assert listed.status_code == 200
    assert plaintext not in listed.text
    assert "token_hash" not in listed.text

    provider_secret = "provider-secret-that-must-never-be-returned"
    provider = api_client.post(
        "/api/v1/admin/provider-keys",
        headers=admin_headers(api_client),
        json={"provider": "gemini", "alias": "primary", "secret": provider_secret},
    )
    assert provider.status_code == 201
    assert provider_secret not in provider.text
    assert "encrypted_secret" not in provider.text

    with psycopg.connect(database_url) as connection:
        token_row = connection.execute(
            "SELECT token_hash FROM api_tokens WHERE id = %s", (created_token.json()["id"],)
        ).fetchone()
        provider_row = connection.execute(
            "SELECT encrypted_secret FROM provider_keys WHERE id = %s", (provider.json()["id"],)
        ).fetchone()
    assert token_row is not None and plaintext not in str(token_row[0])
    assert provider_row is not None and provider_secret.encode() not in bytes(provider_row[0])


def test_validation_errors_do_not_echo_rejected_password(api_client: TestClient) -> None:
    rejected_password = "tiny-secret"
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": "invalid@example.com", "password": rejected_password, "display_name": "X"},
    )
    assert response.status_code == 422
    assert rejected_password not in response.text

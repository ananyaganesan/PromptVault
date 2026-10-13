"""Test-only SMTP capture; membership still requires explicit API acceptance."""

from typing import Any

from fastapi.testclient import TestClient

TOKENS: dict[str, str] = {}


def capture_invitation(settings: Any, recipient: str, token: str, *args: Any) -> None:
    TOKENS[recipient] = token


def accept_invitation(client: TestClient, email: str, headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/project-invitations/accept", headers=headers, json={"token": TOKENS[email]}
    )
    assert response.status_code == 200, response.text

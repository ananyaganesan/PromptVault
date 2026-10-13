"""Invitations confer access only after recipient acceptance."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
import pytest
from api.app.email import EmailDeliveryError
from api.tests.integration.test_projects_prompts_versions import (
    create_project,
    domain_client,
    register_user,
)
from fastapi.testclient import TestClient
from tests.invitation_support import TOKENS

__all__ = ["domain_client"]


def invite(client: TestClient) -> tuple[Any, Any, Any, Any, Any]:
    _, owner_headers = register_user(client, "invite-owner")
    user, headers = register_user(client, "invite-recipient")
    project = create_project(client, owner_headers)
    response = client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": user["email"]},
    )
    assert response.status_code == 201, response.text
    assert "token" not in response.text
    return project, owner_headers, user, headers, response.json()


def accept(client: TestClient, email: str, headers: Any) -> Any:
    return client.post(
        "/api/v1/project-invitations/accept", headers=headers, json={"token": TOKENS[email]}
    )


@pytest.mark.database
def test_pending_invitation_is_not_membership_and_only_recipient_can_accept(
    domain_client: TestClient,
    seeded_database_url: str,
) -> None:
    project, owner_headers, user, headers, invitation = invite(domain_client)
    _, outsider_headers = register_user(domain_client, "invite-outsider")
    path = f"/api/v1/projects/{project['id']}"
    assert domain_client.get(path, headers=headers).status_code == 403
    assert domain_client.get(path, headers=owner_headers).json()["member_count"] == 1
    assert project["id"] not in {
        item["id"]
        for item in domain_client.get("/api/v1/projects", headers=headers).json()["items"]
    }
    assert domain_client.get(f"{path}/invitations", headers=headers).status_code == 403
    pending = domain_client.get(f"{path}/invitations", headers=owner_headers).json()
    assert [item["id"] for item in pending] == [invitation["id"]]
    assert accept(domain_client, user["email"], outsider_headers).status_code == 403
    assert accept(domain_client, user["email"], owner_headers).status_code == 403
    assert accept(domain_client, user["email"], {}).status_code == 401
    assert accept(domain_client, user["email"], headers).status_code == 200
    assert accept(domain_client, user["email"], headers).status_code == 410
    assert domain_client.get(path, headers=headers).status_code == 200
    assert domain_client.get(path, headers=owner_headers).json()["member_count"] == 2
    assert domain_client.get(f"{path}/invitations", headers=owner_headers).json() == []
    with psycopg.connect(seeded_database_url) as connection:
        row = connection.execute(
            "SELECT token_hash, accepted_at FROM project_invitations WHERE id=%s",
            (invitation["id"],),
        ).fetchone()
        assert row and row[0] != TOKENS[user["email"]] and row[1] is not None
        audit = connection.execute(
            "SELECT before_data, after_data FROM audit_events WHERE entity_id=%s",
            (invitation["id"],),
        ).fetchall()
        assert audit and "token_hash" not in str(audit) and TOKENS[user["email"]] not in str(audit)


@pytest.mark.database
@pytest.mark.parametrize("action", ["expire", "cancel"])
def test_expired_or_cancelled_invites_never_grant_access(
    domain_client: TestClient,
    seeded_database_url: str,
    action: str,
) -> None:
    project, owner_headers, user, headers, invitation = invite(domain_client)
    old_token = TOKENS[user["email"]]
    path = f"/api/v1/projects/{project['id']}"
    if action == "expire":
        with psycopg.connect(seeded_database_url) as connection:
            connection.execute(
                """UPDATE project_invitations SET created_at=now()-interval '8 days',
                expires_at=now()-interval '1 day' WHERE id=%s""",
                (invitation["id"],),
            )
    else:
        url = f"{path}/invitations/{invitation['id']}"
        assert domain_client.delete(url, headers=headers).status_code == 403
        assert domain_client.delete(url, headers=owner_headers).status_code == 204
    assert accept(domain_client, user["email"], headers).status_code == 410
    assert domain_client.get(path, headers=headers).status_code == 403
    new = domain_client.post(
        f"{path}/members", headers=owner_headers, json={"email": user["email"]}
    )
    assert new.status_code == 201
    assert TOKENS[user["email"]] != old_token
    assert accept(domain_client, user["email"], headers).status_code == 200


@pytest.mark.database
def test_duplicate_pending_and_simultaneous_acceptance(
    domain_client: TestClient,
) -> None:
    project, owner_headers, user, headers, _ = invite(domain_client)
    duplicate = domain_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": user["email"]},
    )
    assert duplicate.status_code == 409
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: accept(domain_client, user["email"], headers), range(2))
        )
    assert sorted(response.status_code for response in results) == [200, 410]
    assert (
        domain_client.get(f"/api/v1/projects/{project['id']}/members", headers=headers).json()[
            "total"
        ]
        == 2
    )


@pytest.mark.database
def test_email_failure_rolls_back_invitation_and_membership(
    domain_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, owner_headers = register_user(domain_client, "mail-fail-owner")
    user, headers = register_user(domain_client, "mail-fail-member")
    project = create_project(domain_client, owner_headers)

    def fail(*args: Any) -> None:
        raise EmailDeliveryError("delivery failed")

    monkeypatch.setattr("api.app.services.projects.send_project_invitation_email", fail)
    path = f"/api/v1/projects/{project['id']}"
    response = domain_client.post(
        f"{path}/members", headers=owner_headers, json={"email": user["email"]}
    )
    assert response.status_code == 503
    assert domain_client.get(f"{path}/invitations", headers=owner_headers).json() == []
    assert domain_client.get(path, headers=owner_headers).json()["member_count"] == 1
    assert domain_client.get(path, headers=headers).status_code == 403


@pytest.mark.database
@pytest.mark.parametrize("inactive", ["inviter", "recipient"])
def test_inactive_accounts_cannot_use_pending_invitations(
    domain_client: TestClient,
    seeded_database_url: str,
    inactive: str,
) -> None:
    project, owner_headers, user, headers, invitation = invite(domain_client)
    with psycopg.connect(seeded_database_url) as connection:
        if inactive == "recipient":
            user_id = user["id"]
        else:
            user_id = connection.execute(
                "SELECT invited_by FROM project_invitations WHERE id=%s", (invitation["id"],)
            ).fetchone()[0]
        connection.execute("UPDATE users SET is_active=false WHERE id=%s", (user_id,))
    assert accept(domain_client, user["email"], headers).status_code in {401, 403, 410}
    with psycopg.connect(seeded_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM project_members WHERE project_id=%s AND user_id=%s",
                (project["id"], user["id"]),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.database
def test_acceptance_and_cancellation_have_one_winner(domain_client: TestClient) -> None:
    project, owner_headers, user, headers, invitation = invite(domain_client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        accepted = executor.submit(accept, domain_client, user["email"], headers)
        cancelled = executor.submit(
            domain_client.delete,
            f"/api/v1/projects/{project['id']}/invitations/{invitation['id']}",
            headers=owner_headers,
        )
        statuses = (accepted.result().status_code, cancelled.result().status_code)
    assert statuses in {(200, 404), (410, 204)}
    visible = domain_client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    assert visible.status_code == (200 if statuses[0] == 200 else 403)

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient
from tests.auth_support import create_verified_test_user, seed_owned_project
from tests.invitation_support import accept_invitation


@pytest.fixture(scope="module")
def deployment_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    with TestClient(create_app(settings)) as client:
        from tests.provider_support import seed_gemini_test_credential
        seed_gemini_test_credential(client.app.state.settings)
        yield client


def register(client: TestClient, label: str) -> tuple[dict[str, object], dict[str, str]]:
    return create_verified_test_user(client, label)


def login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_prompt(
    client: TestClient, headers: dict[str, str]
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    project_response = seed_owned_project(
        client, headers, {"name": "Deploy Workspace", "key": f"deploy-{uuid4().hex}"}
    )
    project = project_response
    prompt_response = client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "support-reply",
            "name": "Support Reply",
            "template_body": "Version one for {{name}}.",
            "model_config": {
                "provider": "gemini",
                "model": "gemini-3.5-flash-lite",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Initial",
        },
    )
    assert prompt_response.status_code == 201
    prompt = prompt_response.json()
    return project, prompt, prompt["latest_version"]


@pytest.mark.database
def test_staging_is_immediate_and_production_requires_atomic_admin_review(
    deployment_client: TestClient,
) -> None:
    _, owner_headers = register(deployment_client, "deployment-owner")
    _, outsider_headers = register(deployment_client, "deployment-outsider")
    admin_headers = login_admin(deployment_client)
    project, prompt, version = create_prompt(deployment_client, owner_headers)

    development = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "dev"},
    )
    assert development.status_code == 201
    assert development.json()["status"] == "active"
    assert development.json()["activated_at"] is not None

    staging = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "staging"},
    )
    assert staging.status_code == 201
    assert staging.json()["status"] == "active"
    assert staging.json()["activated_at"] is not None

    production = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={
            "version_id": version["id"],
            "environment": "prod",
            "request_note": "Ready for production",
        },
    )
    assert production.status_code == 201
    pending = production.json()
    assert pending["status"] == "pending"
    assert pending["project_id"] == project["id"]

    hidden = deployment_client.get(f"/api/v1/deployments/{pending['id']}", headers=outsider_headers)
    assert hidden.status_code == 404

    denied = deployment_client.post(
        f"/api/v1/admin/deployments/{pending['id']}/approve",
        headers=owner_headers,
        json={"review_note": "attempt"},
    )
    assert denied.status_code == 403

    queue = deployment_client.get("/api/v1/admin/deployments/pending", headers=admin_headers)
    assert queue.status_code == 200
    assert pending["id"] in {item["id"] for item in queue.json()["items"]}

    detail = deployment_client.get(
        f"/api/v1/admin/deployments/{pending['id']}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["requested_version"]["id"] == version["id"]
    assert "recent_runs" in detail.json()

    approved = deployment_client.post(
        f"/api/v1/admin/deployments/{pending['id']}/approve",
        headers=admin_headers,
        json={"review_note": "Reviewed"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"

    repeated = deployment_client.post(
        f"/api/v1/admin/deployments/{pending['id']}/reject",
        headers=admin_headers,
        json={"review_note": "Too late"},
    )
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "already_reviewed"

    history = deployment_client.get(
        "/api/v1/deployments",
        headers=owner_headers,
        params={"prompt_id": prompt["id"], "environment": "prod"},
    )
    assert history.status_code == 200
    assert pending["id"] in {item["id"] for item in history.json()["items"]}

    second = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    ).json()
    missing_reason = deployment_client.post(
        f"/api/v1/admin/deployments/{second['id']}/reject",
        headers=admin_headers,
        json={"review_note": "   "},
    )
    assert missing_reason.status_code == 422
    rejected = deployment_client.post(
        f"/api/v1/admin/deployments/{second['id']}/reject",
        headers=admin_headers,
        json={"review_note": "Insufficient evidence"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


@pytest.mark.database
def test_pending_deployment_cancellation_requires_requester(
    deployment_client: TestClient,
) -> None:
    _, owner_headers = register(deployment_client, "cancel-owner")
    member_user, member_headers = register(deployment_client, "cancel-member")
    project, _, version = create_prompt(deployment_client, owner_headers)
    member = deployment_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": member_user["email"]},
    )
    assert member.status_code == 201
    accept_invitation(deployment_client, str(member_user["email"]), member_headers)
    member_token_attempt = deployment_client.post(
        "/api/v1/api-tokens",
        headers=member_headers,
        json={"project_id": project["id"], "name": "Not owner"},
    )
    assert member_token_attempt.status_code == 403
    pending = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    ).json()

    forbidden = deployment_client.post(
        f"/api/v1/deployments/{pending['id']}/cancel", headers=member_headers
    )
    assert forbidden.status_code == 403
    cancelled = deployment_client.post(
        f"/api/v1/deployments/{pending['id']}/cancel", headers=owner_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    repeated = deployment_client.post(
        f"/api/v1/deployments/{pending['id']}/cancel", headers=owner_headers
    )
    assert repeated.status_code == 409


@pytest.mark.database
def test_competing_http_reviews_and_cancel_review_have_one_success(
    deployment_client: TestClient,
) -> None:
    _, owner_headers = register(deployment_client, "http-race-owner")
    admin_headers = login_admin(deployment_client)
    _, _, version = create_prompt(deployment_client, owner_headers)

    pending = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    ).json()
    review_barrier = Barrier(2)

    def approve() -> object:
        review_barrier.wait()
        return deployment_client.post(
            f"/api/v1/admin/deployments/{pending['id']}/approve",
            headers=admin_headers,
            json={},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        review_responses = list(executor.map(lambda _: approve(), range(2)))
    assert sorted(response.status_code for response in review_responses) == [200, 409]
    loser = next(response for response in review_responses if response.status_code == 409)
    assert loser.json()["code"] == "already_reviewed"

    competing = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    ).json()
    transition_barrier = Barrier(2)

    def cancel_or_review(operation: str) -> object:
        transition_barrier.wait()
        if operation == "cancel":
            return deployment_client.post(
                f"/api/v1/deployments/{competing['id']}/cancel",
                headers=owner_headers,
            )
        return deployment_client.post(
            f"/api/v1/admin/deployments/{competing['id']}/approve",
            headers=admin_headers,
            json={},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        transition_responses = list(executor.map(cancel_or_review, ("cancel", "review")))
    assert sorted(response.status_code for response in transition_responses) == [200, 409]
    transition_loser = next(
        response for response in transition_responses if response.status_code == 409
    )
    assert transition_loser.json()["code"] in {"already_reviewed", "invalid_state"}


@pytest.mark.database
def test_runtime_token_is_disclosed_once_scoped_revocable_and_serves_rollback(
    deployment_client: TestClient,
    seeded_database_url: str,
) -> None:
    _, owner_headers = register(deployment_client, "token-owner")
    _, outsider_headers = register(deployment_client, "token-outsider")
    admin_headers = login_admin(deployment_client)
    project, prompt, version_one = create_prompt(deployment_client, owner_headers)
    deployed = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version_one["id"], "environment": "prod"},
    ).json()
    assert (
        deployment_client.post(
            f"/api/v1/admin/deployments/{deployed['id']}/approve",
            headers=admin_headers,
            json={},
        ).status_code
        == 200
    )

    created = deployment_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={
            "project_id": project["id"],
            "name": "Production runtime",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    assert created.status_code == 201
    issued = created.json()
    token = issued.pop("token")
    assert token.startswith("pv_live_")
    assert issued["token_prefix"] == token[:20]
    assert issued["expires_at"] == "2099-01-01T00:00:00Z"
    assert "token_hash" not in created.text

    with psycopg.connect(seeded_database_url) as connection:
        stored = connection.execute(
            "SELECT token_hash FROM api_tokens WHERE id = %s", (issued["id"],)
        ).fetchone()[0]
        audit_document = connection.execute(
            """SELECT actor_user_id, after_data FROM audit_events
               WHERE entity_type = 'api_tokens' AND entity_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (issued["id"],),
        ).fetchone()
    assert token not in stored
    assert len(stored) == 64
    assert str(audit_document[0]) == issued["created_by"]
    assert "token_hash" not in audit_document[1]
    assert token not in str(audit_document[1])

    listed = deployment_client.get(
        "/api/v1/api-tokens",
        headers=owner_headers,
        params={"project_id": project["id"]},
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == issued["id"]
    assert listed.json()["items"][0]["token_prefix"] == token[:20]
    assert listed.json()["items"][0]["expires_at"] == "2099-01-01T00:00:00Z"
    assert '"token":' not in listed.text
    assert "token_hash" not in listed.text
    denied_list = deployment_client.get(
        "/api/v1/api-tokens",
        headers=outsider_headers,
        params={"project_id": project["id"]},
    )
    assert denied_list.status_code == 403

    served = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
        params={"env": "prod"},
    )
    assert served.status_code == 200
    assert served.json()["project_id"] == project["id"]
    assert served.json()["version"]["id"] == version_one["id"]
    assert served.headers["cache-control"] == "private, max-age=30"
    assert "Authorization" in {value.strip() for value in served.headers["vary"].split(",")}
    assert served.headers["etag"]
    conditional = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}", "If-None-Match": served.headers["etag"]},
        params={"env": "prod"},
    )
    assert conditional.status_code == 304
    assert "Authorization" in {value.strip() for value in conditional.headers["vary"].split(",")}
    weak_or_multiple = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={
            "Authorization": f"Bearer {token}",
            "If-None-Match": f'"unrelated", W/{served.headers["etag"]}',
        },
        params={"env": "prod"},
    )
    wildcard = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}", "If-None-Match": "*"},
    )
    assert weak_or_multiple.status_code == 304
    assert wildcard.status_code == 304

    version_two_response = deployment_client.post(
        f"/api/v1/prompts/{prompt['id']}/versions",
        headers=owner_headers,
        json={
            "parent_version_id": version_one["id"],
            "template_body": "Version two for {{name}}.",
            "model_config": version_one["model_config"],
            "commit_message": "Second",
        },
    )
    assert version_two_response.status_code == 201
    version_two = version_two_response.json()
    second_request = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version_two["id"], "environment": "prod"},
    ).json()
    assert (
        deployment_client.post(
            f"/api/v1/admin/deployments/{second_request['id']}/approve",
            headers=admin_headers,
            json={},
        ).status_code
        == 200
    )

    not_earlier = deployment_client.post(
        f"/api/v1/admin/prompts/{prompt['id']}/rollback",
        headers=admin_headers,
        json={"target_version_id": version_two["id"], "reason": "Not actually older"},
    )
    assert not_earlier.status_code == 409
    assert not_earlier.json()["code"] == "invalid_rollback_target"
    unchanged = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["version"]["id"] == version_two["id"]

    rollback = deployment_client.post(
        f"/api/v1/admin/prompts/{prompt['id']}/rollback",
        headers=admin_headers,
        json={"target_version_id": version_one["id"], "reason": "Regression"},
    )
    assert rollback.status_code == 201
    assert rollback.json()["rollback_of_id"] == second_request["id"]
    after = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after.status_code == 200
    assert after.json()["version"]["id"] == version_one["id"]

    revoked = deployment_client.delete(f"/api/v1/api-tokens/{issued['id']}", headers=owner_headers)
    assert revoked.status_code == 204
    rejected = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rejected.status_code == 401
    assert rejected.json()["code"] == "invalid_token"


@pytest.mark.database
def test_runtime_token_cannot_cross_project_or_outlive_expiration(
    deployment_client: TestClient,
    seeded_database_url: str,
) -> None:
    _, owner_headers = register(deployment_client, "scope-owner")
    admin_headers = login_admin(deployment_client)
    project_without_active, prompt_without_active, version_without_active = create_prompt(
        deployment_client, owner_headers
    )
    project_with_active, _, version = create_prompt(deployment_client, owner_headers)
    pending = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "prod"},
    ).json()
    assert (
        deployment_client.post(
            f"/api/v1/admin/deployments/{pending['id']}/approve",
            headers=admin_headers,
            json={},
        ).status_code
        == 200
    )

    no_active_rollback = deployment_client.post(
        f"/api/v1/admin/prompts/{prompt_without_active['id']}/rollback",
        headers=admin_headers,
        json={
            "target_version_id": version_without_active["id"],
            "reason": "No active deployment exists",
        },
    )
    assert no_active_rollback.status_code == 409
    assert no_active_rollback.json()["code"] == "no_active_deployment"

    issued = deployment_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={"project_id": project_without_active["id"], "name": "Scoped"},
    ).json()
    token = issued["token"]
    cross_project = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cross_project.status_code == 404
    assert project_with_active["id"] not in cross_project.text

    project_without_active_request = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version_without_active["id"], "environment": "prod"},
    ).json()
    assert (
        deployment_client.post(
            f"/api/v1/admin/deployments/{project_without_active_request['id']}/approve",
            headers=admin_headers,
            json={},
        ).status_code
        == 200
    )
    other_token = deployment_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={"project_id": project_with_active["id"], "name": "Other project"},
    ).json()["token"]
    first_project = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    second_project = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert first_project.status_code == second_project.status_code == 200
    assert first_project.json()["project_id"] == project_without_active["id"]
    assert second_project.json()["project_id"] == project_with_active["id"]
    for response in (first_project, second_project):
        assert "Authorization" in {value.strip() for value in response.headers["vary"].split(",")}

    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """
            UPDATE api_tokens
            SET created_at = CURRENT_TIMESTAMP - INTERVAL '2 days',
                expires_at = CURRENT_TIMESTAMP - INTERVAL '1 day'
            WHERE id = %s
            """,
            (issued["id"],),
        )
    expired = deployment_client.get(
        "/serve/v1/prompts/support-reply",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired.status_code == 401
    assert expired.json()["code"] == "invalid_token"


@pytest.mark.database
def test_phase4_auth_validation_missing_and_failed_writes_are_safe(
    deployment_client: TestClient,
) -> None:
    _, owner_headers = register(deployment_client, "phase4-errors-owner")
    admin_headers = login_admin(deployment_client)
    project, _, version = create_prompt(deployment_client, owner_headers)

    for method, path in (
        ("get", "/api/v1/deployments"),
        ("post", "/api/v1/deployments"),
        ("get", "/api/v1/api-tokens"),
        ("post", "/api/v1/api-tokens"),
        ("get", "/api/v1/admin/deployments/pending"),
    ):
        response = deployment_client.request(method, path, json={})
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"
    unauthenticated_serve = deployment_client.get("/serve/v1/prompts/support-reply")
    assert unauthenticated_serve.status_code == 401
    assert unauthenticated_serve.json()["code"] == "unauthorized"

    unknown = deployment_client.get(f"/api/v1/deployments/{uuid4()}", headers=owner_headers)
    invalid_filter = deployment_client.get(
        "/api/v1/deployments", headers=owner_headers, params={"unknown": "value"}
    )
    invalid_environment = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version["id"], "environment": "production"},
    )
    assert unknown.status_code == 404
    assert invalid_filter.status_code == 400
    assert invalid_environment.status_code == 422

    before_deployments = deployment_client.get(
        "/api/v1/deployments",
        headers=owner_headers,
        params={"project_id": project["id"]},
    ).json()["total"]
    missing_version = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": str(uuid4()), "environment": "staging"},
    )
    after_deployments = deployment_client.get(
        "/api/v1/deployments",
        headers=owner_headers,
        params={"project_id": project["id"]},
    ).json()["total"]
    assert missing_version.status_code == 404
    assert after_deployments == before_deployments

    before_tokens = deployment_client.get(
        "/api/v1/api-tokens",
        headers=owner_headers,
        params={"project_id": project["id"]},
    ).json()["total"]
    expired_create = deployment_client.post(
        "/api/v1/api-tokens",
        headers=owner_headers,
        json={
            "project_id": project["id"],
            "name": "Already expired",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
    )
    after_tokens = deployment_client.get(
        "/api/v1/api-tokens",
        headers=owner_headers,
        params={"project_id": project["id"]},
    ).json()["total"]
    assert expired_create.status_code == 422
    assert after_tokens == before_tokens

    missing_admin_detail = deployment_client.get(
        f"/api/v1/admin/deployments/{uuid4()}", headers=admin_headers
    )
    assert missing_admin_detail.status_code == 404


@pytest.mark.database
def test_rollback_database_failure_reverts_state_and_audit_atomically(
    deployment_client: TestClient,
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    _, owner_headers = register(deployment_client, "rollback-fault-owner")
    admin_headers = login_admin(deployment_client)
    _, prompt, version_one = create_prompt(deployment_client, owner_headers)
    version_two_response = deployment_client.post(
        f"/api/v1/prompts/{prompt['id']}/versions",
        headers=owner_headers,
        json={
            "parent_version_id": version_one["id"],
            "template_body": "Version two for {{name}}.",
            "model_config": version_one["model_config"],
            "commit_message": "Second",
        },
    )
    assert version_two_response.status_code == 201
    version_two = version_two_response.json()
    pending = deployment_client.post(
        "/api/v1/deployments",
        headers=owner_headers,
        json={"version_id": version_two["id"], "environment": "prod"},
    ).json()
    active = deployment_client.post(
        f"/api/v1/admin/deployments/{pending['id']}/approve",
        headers=admin_headers,
        json={},
    )
    assert active.status_code == 200

    with psycopg.connect(seeded_database_url) as connection:
        before = connection.execute(
            """
            SELECT
                (SELECT id FROM deployment_context
                 WHERE prompt_id = %s AND environment = 'prod' AND status = 'active'),
                (SELECT count(*) FROM deployment_context WHERE prompt_id = %s),
                (SELECT count(*) FROM audit_events
                 WHERE entity_type = 'deployments'
                   AND entity_id IN (SELECT id FROM deployment_context WHERE prompt_id = %s))
            """,
            (prompt["id"], prompt["id"], prompt["id"]),
        ).fetchone()
        connection.execute(
            """
            CREATE OR REPLACE FUNCTION test_fail_rollback_insert()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.rollback_of_id IS NOT NULL THEN
                    RAISE EXCEPTION 'forced rollback insert failure' USING ERRCODE = 'P0001';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER test_fail_rollback_insert
            BEFORE INSERT ON deployments
            FOR EACH ROW EXECUTE FUNCTION test_fail_rollback_insert();
            """
        )

    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    try:
        with TestClient(create_app(settings), raise_server_exceptions=False) as safe_client:
            failed = safe_client.post(
                f"/api/v1/admin/prompts/{prompt['id']}/rollback",
                headers=admin_headers,
                json={
                    "target_version_id": version_one["id"],
                    "reason": "Trigger the transactional failure",
                },
            )
        assert failed.status_code == 500
        assert failed.json()["code"] == "internal_error"
        assert "forced rollback" not in failed.text

        with psycopg.connect(seeded_database_url) as connection:
            after = connection.execute(
                """
                SELECT
                    (SELECT id FROM deployment_context
                     WHERE prompt_id = %s AND environment = 'prod' AND status = 'active'),
                    (SELECT count(*) FROM deployment_context WHERE prompt_id = %s),
                    (SELECT count(*) FROM audit_events
                     WHERE entity_type = 'deployments'
                       AND entity_id IN (SELECT id FROM deployment_context WHERE prompt_id = %s))
                """,
                (prompt["id"], prompt["id"], prompt["id"]),
            ).fetchone()
        assert after == before
        assert str(after[0]) == active.json()["id"]
    finally:
        with psycopg.connect(seeded_database_url) as connection:
            connection.execute("DROP TRIGGER IF EXISTS test_fail_rollback_insert ON deployments")
            connection.execute("DROP FUNCTION IF EXISTS test_fail_rollback_insert()")

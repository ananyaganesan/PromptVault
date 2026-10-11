from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.security import decrypt_provider_secret
from fastapi.testclient import TestClient

SEEDED_ADMIN_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture(scope="module")
def admin_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "provider_encryption_key": "test-provider-encryption-key-at-least-32-chars",
        }
    )
    with TestClient(create_app(settings)) as client:
        yield client


def register(client: TestClient, label: str) -> tuple[dict[str, object], dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{label}-{uuid4()}@example.com",
            "password": "CorrectHorse2026!",
            "display_name": label.replace("-", " ").title(),
        },
    )
    assert response.status_code == 201
    session = response.json()
    return session["user"], {"Authorization": f"Bearer {session['access_token']}"}


def login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login_user(client: TestClient, email: object) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "CorrectHorse2026!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_project_and_run(
    client: TestClient, headers: dict[str, str]
) -> tuple[dict[str, object], dict[str, object]]:
    project_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Governance Workspace", "key": f"govern-{uuid4().hex}"},
    )
    assert project_response.status_code == 201
    project = project_response.json()
    prompt_response = client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "governance-prompt",
            "name": "Governance Prompt",
            "template_body": "Hello {{name}}.",
            "model_config": {
                "provider": "mock",
                "model": "deterministic-v1",
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Initial",
        },
    )
    assert prompt_response.status_code == 201
    version = prompt_response.json()["latest_version"]
    run_response = client.post(
        "/api/v1/runs",
        headers=headers,
        json={"version_id": version["id"], "variables": {"name": "Admin"}},
    )
    assert run_response.status_code == 201
    return project, run_response.json()


@pytest.mark.database
def test_admin_users_dashboard_and_organization_runs(
    admin_client: TestClient,
    seeded_database_url: str,
) -> None:
    user, user_headers = register(admin_client, "governed-user")
    admin_headers = login_admin(admin_client)
    project, run = create_project_and_run(admin_client, user_headers)

    denied = admin_client.get("/api/v1/admin/users", headers=user_headers)
    anonymous = admin_client.get("/api/v1/admin/dashboard")
    assert denied.status_code == 403
    assert anonymous.status_code == 401

    users = admin_client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
        params={"search": user["email"], "role": "user", "is_active": True},
    )
    assert users.status_code == 200
    assert users.json()["total"] == 1
    assert users.json()["items"][0]["project_count"] == 1

    promoted = admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert admin_client.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    user_headers = login_user(admin_client, user["email"])
    self_deactivated = admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=user_headers,
        json={"is_active": False},
    )
    assert self_deactivated.status_code == 200
    assert self_deactivated.json()["is_active"] is False
    assert admin_client.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    reactivated = admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers,
        json={"is_active": True},
    )
    assert reactivated.status_code == 200
    assert admin_client.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    user_headers = login_user(admin_client, user["email"])
    self_demoted = admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=user_headers,
        json={"role": "user"},
    )
    assert self_demoted.status_code == 200
    assert self_demoted.json()["role"] == "user"
    stale_admin_session = admin_client.get("/api/v1/auth/me", headers=user_headers)
    assert stale_admin_session.status_code == 401
    assert stale_admin_session.json()["code"] == "invalid_token"
    user_headers = login_user(admin_client, user["email"])
    assert admin_client.get("/api/v1/auth/me", headers=user_headers).json()["role"] == "user"
    assert admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers,
        json={"role": "admin"},
    ).status_code == 200
    deactivated = admin_client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    inactive_session = admin_client.get("/api/v1/auth/me", headers=user_headers)
    assert inactive_session.status_code == 401
    assert inactive_session.json()["code"] == "invalid_token"

    with psycopg.connect(seeded_database_url) as connection:
        other_admins = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' AND id <> %s", (SEEDED_ADMIN_ID,)
        ).fetchall()
        for (other_admin_id,) in other_admins:
            connection.execute(
                "UPDATE users SET role = 'user', is_active = FALSE WHERE id = %s",
                (other_admin_id,),
            )
    last_admin = admin_client.patch(
        f"/api/v1/admin/users/{SEEDED_ADMIN_ID}",
        headers=admin_headers,
        json={"role": "user"},
    )
    assert last_admin.status_code == 409
    assert last_admin.json()["code"] == "last_admin"

    dashboard = admin_client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert dashboard.status_code == 200
    metrics = dashboard.json()
    assert metrics["user_count"] >= 2
    assert metrics["project_count"] >= 1
    assert metrics["run_count"] >= 1
    assert Decimal(metrics["total_spend"]) >= Decimal(run["cost"])
    assert any(item["model"] == "deterministic-v1" for item in metrics["spend_by_model"])
    with psycopg.connect(seeded_database_url) as connection:
        expected = connection.execute(
            """
            SELECT count(*) AS run_count,
                   count(*) FILTER (WHERE status = 'completed') AS completed,
                   count(*) FILTER (WHERE status = 'failed') AS failed,
                   count(*) FILTER (WHERE status = 'blocked') AS blocked,
                   COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0) AS spend
            FROM runs
            WHERE created_at >= date_trunc('month', CURRENT_TIMESTAMP)
              AND created_at < date_trunc('month', CURRENT_TIMESTAMP) + INTERVAL '1 month'
            """
        ).fetchone()
    assert metrics["run_count"] == expected[0]
    assert metrics["completed_run_count"] == expected[1]
    assert metrics["failed_run_count"] == expected[2]
    assert metrics["blocked_run_count"] == expected[3]
    assert Decimal(metrics["total_spend"]) == expected[4]

    runs = admin_client.get(
        "/api/v1/admin/runs",
        headers=admin_headers,
        params={
            "user_id": run["user_id"],
            "project_id": project["id"],
            "prompt_id": run["prompt_id"],
            "model": run["model"],
            "status": run["status"],
            "from": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "to": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert runs.status_code == 200
    assert run["id"] in {item["id"] for item in runs.json()["items"]}

    searched_runs = admin_client.get(
        "/api/v1/admin/runs",
        headers=admin_headers,
        params={"search": run["id"], "page": 1, "page_size": 1},
    )
    assert searched_runs.status_code == 200
    assert searched_runs.json()["total"] == 1
    assert searched_runs.json()["items"][0]["id"] == run["id"]


@pytest.mark.database
def test_concurrent_admin_cross_deactivation_returns_safe_loser_response(
    admin_client: TestClient,
    seeded_database_url: str,
) -> None:
    first, first_headers = register(admin_client, "api-race-admin-one")
    second, second_headers = register(admin_client, "api-race-admin-two")
    seeded_headers = login_admin(admin_client)
    for user in (first, second):
        promoted = admin_client.patch(
            f"/api/v1/admin/users/{user['id']}",
            headers=seeded_headers,
            json={"role": "admin"},
        )
        assert promoted.status_code == 200
    first_headers = login_user(admin_client, first["email"])
    second_headers = login_user(admin_client, second["email"])

    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """UPDATE users SET role = 'user', is_active = FALSE
               WHERE role = 'admin' AND id NOT IN (%s, %s)""",
            (first["id"], second["id"]),
        )

    barrier = Barrier(2)

    def deactivate(headers: dict[str, str], target_id: object) -> int:
        barrier.wait()
        try:
            return admin_client.patch(
                f"/api/v1/admin/users/{target_id}",
                headers=headers,
                json={"is_active": False},
            ).status_code
        except Exception:  # pragma: no cover - proves the pre-fix server exception
            return 500

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(
                executor.map(
                    lambda arguments: deactivate(*arguments),
                    (
                        (first_headers, second["id"]),
                        (second_headers, first["id"]),
                    ),
                )
            )
        assert sorted(statuses) == [200, 401]
        with psycopg.connect(seeded_database_url) as connection:
            active_count = connection.execute(
                "SELECT count(*) FROM users WHERE role = 'admin' AND is_active"
            ).fetchone()[0]
        assert active_count == 1
    finally:
        with psycopg.connect(seeded_database_url) as connection:
            connection.execute(
                "UPDATE users SET role = 'admin', is_active = TRUE WHERE id = %s",
                (SEEDED_ADMIN_ID,),
            )
            connection.execute(
                "UPDATE users SET role = 'user', is_active = FALSE WHERE id IN (%s, %s)",
                (first["id"], second["id"]),
            )


@pytest.mark.database
def test_admin_provider_keys_budgets_and_effective_pricing(
    admin_client: TestClient,
    seeded_database_url: str,
) -> None:
    _, owner_headers = register(admin_client, "governance-owner")
    admin_headers = login_admin(admin_client)
    project, _ = create_project_and_run(admin_client, owner_headers)
    provider = "gemini"
    provider_alias = f"primary-{uuid4().hex}"
    plaintext = "  super-secret-provider-credential  "

    unsupported = admin_client.post(
        "/api/v1/admin/provider-keys",
        headers=admin_headers,
        json={"provider": "openai", "alias": "unused", "secret": plaintext},
    )
    assert unsupported.status_code == 422

    created_key = admin_client.post(
        "/api/v1/admin/provider-keys",
        headers=admin_headers,
        json={"provider": provider, "alias": provider_alias, "secret": plaintext},
    )
    assert created_key.status_code == 201
    key_metadata = created_key.json()
    assert plaintext not in created_key.text
    assert "encrypted_secret" not in created_key.text
    with psycopg.connect(seeded_database_url) as connection:
        encrypted = connection.execute(
            "SELECT encrypted_secret FROM provider_keys WHERE id = %s",
            (key_metadata["id"],),
        ).fetchone()[0]
    assert plaintext.encode() not in encrypted
    assert (
        decrypt_provider_secret(
            bytes(encrypted), "test-provider-encryption-key-at-least-32-chars"
        )
        == plaintext
    )

    keys = admin_client.get("/api/v1/admin/provider-keys", headers=admin_headers)
    assert keys.status_code == 200
    assert key_metadata["id"] in {item["id"] for item in keys.json()["items"]}
    assert plaintext not in keys.text
    assert "encrypted_secret" not in keys.text
    duplicate_key = admin_client.post(
        "/api/v1/admin/provider-keys",
        headers=admin_headers,
        json={
            "provider": provider,
            "alias": provider_alias,
            "secret": "different-secret",
        },
    )
    assert duplicate_key.status_code == 409
    filtered_keys = admin_client.get(
        "/api/v1/admin/provider-keys",
        headers=admin_headers,
        params={"provider": provider},
    )
    assert key_metadata["id"] in {
        item["id"] for item in filtered_keys.json()["items"]
    }
    revoked_key = admin_client.delete(
        f"/api/v1/admin/provider-keys/{key_metadata['id']}", headers=admin_headers
    )
    assert revoked_key.status_code == 204

    created_budget = admin_client.post(
        "/api/v1/admin/budgets",
        headers=admin_headers,
        json={
            "project_id": project["id"],
            "monthly_limit": "125.500000",
            "timezone": "Asia/Kolkata",
        },
    )
    assert created_budget.status_code == 201
    budget = created_budget.json()
    assert Decimal(budget["monthly_limit"]) == Decimal("125.500000")
    duplicate_budget = admin_client.post(
        "/api/v1/admin/budgets",
        headers=admin_headers,
        json={"project_id": project["id"], "monthly_limit": "5", "timezone": "UTC"},
    )
    assert duplicate_budget.status_code == 409
    filtered_budgets = admin_client.get(
        "/api/v1/admin/budgets",
        headers=admin_headers,
        params={"project_id": project["id"]},
    )
    assert filtered_budgets.json()["total"] == 1
    invalid_target = admin_client.post(
        "/api/v1/admin/budgets",
        headers=admin_headers,
        json={
            "user_id": str(SEEDED_ADMIN_ID),
            "project_id": project["id"],
            "monthly_limit": "5",
        },
    )
    assert invalid_target.status_code == 422
    updated_budget = admin_client.patch(
        f"/api/v1/admin/budgets/{budget['id']}",
        headers=admin_headers,
        json={"monthly_limit": "80", "timezone": "UTC"},
    )
    assert updated_budget.status_code == 200
    assert Decimal(updated_budget.json()["monthly_limit"]) == Decimal("80")
    assert admin_client.delete(
        f"/api/v1/admin/budgets/{budget['id']}", headers=admin_headers
    ).status_code == 204

    model = f"governance-model-{uuid4().hex}"
    effective_from = datetime.now(UTC) + timedelta(days=1)
    pricing = admin_client.post(
        "/api/v1/admin/model-pricing",
        headers=admin_headers,
        json={
            "provider": provider,
            "model": model,
            "input_price_per_million": "1.25",
            "output_price_per_million": "3.75",
            "effective_from": effective_from.isoformat(),
        },
    )
    assert pricing.status_code == 201
    price = pricing.json()
    assert price["model"] == model
    overlapping = admin_client.post(
        "/api/v1/admin/model-pricing",
        headers=admin_headers,
        json={
            "provider": provider,
            "model": model,
            "input_price_per_million": "2",
            "output_price_per_million": "4",
            "effective_from": (effective_from + timedelta(hours=1)).isoformat(),
        },
    )
    assert overlapping.status_code == 409
    history = admin_client.get(
        "/api/v1/admin/model-pricing",
        headers=admin_headers,
        params={"provider": provider, "model": model},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == price["id"]


@pytest.mark.database
def test_admin_audit_is_filterable_attributed_and_redacted(
    admin_client: TestClient,
) -> None:
    admin_headers = login_admin(admin_client)
    provider = "gemini"
    provider_alias = f"audit-{uuid4().hex}"
    secret = "audit-secret-must-never-appear"
    created = admin_client.post(
        "/api/v1/admin/provider-keys",
        headers={**admin_headers, "X-Request-ID": "governance-audit-request"},
        json={"provider": provider, "alias": provider_alias, "secret": secret},
    )
    assert created.status_code == 201

    audit = admin_client.get(
        "/api/v1/admin/audit",
        headers=admin_headers,
        params={
            "actor_id": str(SEEDED_ADMIN_ID),
            "action": "insert",
            "entity_type": "provider_keys",
            "entity_id": created.json()["id"],
            "from": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "to": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert audit.status_code == 200
    event = next(
        item for item in audit.json()["items"] if item["entity_id"] == created.json()["id"]
    )
    assert event["actor_user_id"] == str(SEEDED_ADMIN_ID)
    assert event["request_id"] == "governance-audit-request"
    assert event["action"] == "insert"
    assert secret not in audit.text
    assert "encrypted_secret" not in audit.text


@pytest.mark.database
def test_admin_maintenance_reports_and_executes_idempotent_operations(
    admin_client: TestClient,
) -> None:
    _, user_headers = register(admin_client, "maintenance-user")
    admin_headers = login_admin(admin_client)
    assert admin_client.get("/api/v1/admin/maintenance", headers=user_headers).status_code == 403

    status_response = admin_client.get(
        "/api/v1/admin/maintenance", headers=admin_headers
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert {item["name"] for item in status_body["materialized_views"]} == {
        "organization_monthly_metrics",
        "user_monthly_metrics",
    }
    assert status_body["run_partitions"]
    assert {item["name"] for item in status_body["maintenance_jobs"]} == {
        "refresh_materialized_views",
        "create_next_partition",
    }
    assert "provider_secrets" not in status_response.text

    refreshed = admin_client.post(
        "/api/v1/admin/maintenance/refresh-views", headers=admin_headers
    )
    assert refreshed.status_code == 202
    assert refreshed.json()["status"] == "completed"
    partition = admin_client.post(
        "/api/v1/admin/maintenance/create-next-partition", headers=admin_headers
    )
    repeated = admin_client.post(
        "/api/v1/admin/maintenance/create-next-partition", headers=admin_headers
    )
    assert partition.status_code == repeated.status_code == 200
    assert partition.json()["partition_name"] == repeated.json()["partition_name"]

    updated_status = admin_client.get(
        "/api/v1/admin/maintenance", headers=admin_headers
    ).json()
    assert all(
        item["status"] == "completed" and item["last_completed_at"] is not None
        for item in updated_status["maintenance_jobs"]
    )

    maintenance_audit = admin_client.get(
        "/api/v1/admin/audit",
        headers=admin_headers,
        params={"actor_id": str(SEEDED_ADMIN_ID)},
    )
    assert maintenance_audit.status_code == 200
    maintenance_actions = {
        (item["action"], item["entity_type"], item["request_id"])
        for item in maintenance_audit.json()["items"]
    }
    assert any(
        action == "refresh" and entity_type == "materialized_views"
        for action, entity_type, _ in maintenance_actions
    )
    assert any(
        action == "create" and entity_type == "run_partitions"
        for action, entity_type, _ in maintenance_actions
    )


@pytest.mark.database
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users",
        "/api/v1/admin/budgets",
        "/api/v1/admin/provider-keys",
        "/api/v1/admin/model-pricing",
        "/api/v1/admin/runs",
        "/api/v1/admin/audit",
        "/api/v1/admin/maintenance",
    ],
)
def test_every_governance_read_requires_super_admin(
    admin_client: TestClient,
    path: str,
) -> None:
    _, user_headers = register(admin_client, f"denied-{uuid4().hex}")

    anonymous = admin_client.get(path)
    forbidden = admin_client.get(path, headers=user_headers)

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"


@pytest.mark.database
@pytest.mark.parametrize("path", ["/api/v1/admin/runs", "/api/v1/admin/audit"])
def test_admin_date_filters_require_timezone_offsets(
    admin_client: TestClient,
    path: str,
) -> None:
    admin_headers = login_admin(admin_client)

    naive = admin_client.get(
        path,
        headers=admin_headers,
        params={"from": "2026-09-01T00:00:00"},
    )
    mixed = admin_client.get(
        path,
        headers=admin_headers,
        params={
            "from": "2026-09-01T00:00:00",
            "to": "2026-10-01T00:00:00Z",
        },
    )

    assert naive.status_code == 400
    assert naive.json()["code"] == "invalid_filter"
    assert mixed.status_code == 400
    assert mixed.json()["code"] == "invalid_filter"


@pytest.mark.database
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("PATCH", f"/api/v1/admin/users/{uuid4()}", {"is_active": False}),
        (
            "POST",
            "/api/v1/admin/budgets",
            {"user_id": str(SEEDED_ADMIN_ID), "monthly_limit": "1"},
        ),
        ("PATCH", f"/api/v1/admin/budgets/{uuid4()}", {"monthly_limit": "1"}),
        ("DELETE", f"/api/v1/admin/budgets/{uuid4()}", None),
        (
            "POST",
            "/api/v1/admin/provider-keys",
            {"provider": "denied", "alias": "primary", "secret": "credential"},
        ),
        ("DELETE", f"/api/v1/admin/provider-keys/{uuid4()}", None),
        (
            "POST",
            "/api/v1/admin/model-pricing",
            {
                "provider": "denied",
                "model": "denied",
                "input_price_per_million": "1",
                "output_price_per_million": "1",
                "effective_from": "2027-01-01T00:00:00Z",
            },
        ),
        ("POST", "/api/v1/admin/maintenance/refresh-views", None),
        ("POST", "/api/v1/admin/maintenance/create-next-partition", None),
    ],
)
def test_every_governance_mutation_requires_super_admin(
    admin_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    _, user_headers = register(admin_client, f"mutation-denied-{uuid4().hex}")

    anonymous = admin_client.request(method, path, json=payload)
    forbidden = admin_client.request(method, path, headers=user_headers, json=payload)

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"


@pytest.mark.database
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("PATCH", f"/api/v1/admin/users/{uuid4()}", {"is_active": False}),
        ("PATCH", f"/api/v1/admin/budgets/{uuid4()}", {"monthly_limit": "1"}),
        ("DELETE", f"/api/v1/admin/budgets/{uuid4()}", None),
        ("DELETE", f"/api/v1/admin/provider-keys/{uuid4()}", None),
    ],
)
def test_governance_mutations_return_safe_not_found(
    admin_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    response = admin_client.request(
        method,
        path,
        headers=login_admin(admin_client),
        json=payload,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"

import json
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import psycopg
import pytest
from api.app.config import Settings
from api.app.main import create_app
from api.app.security import encrypt_provider_secret
from fastapi.testclient import TestClient
from tests.auth_support import create_verified_test_user, seed_owned_project
from tests.invitation_support import accept_invitation


@pytest.fixture(scope="module")
def run_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    with TestClient(create_app(settings)) as client:
        from tests.provider_support import seed_gemini_test_credential

        seed_gemini_test_credential(client.app.state.settings)
        yield client


@pytest.fixture(scope="module")
def single_connection_run_client(
    test_settings: Settings,
    seeded_database_url: str,
) -> Iterator[TestClient]:
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "db_pool_min_size": 0,
            "db_pool_max_size": 1,
            "db_pool_timeout_seconds": 0.05,
        }
    )
    with TestClient(create_app(settings)) as client:
        from tests.provider_support import seed_gemini_test_credential

        seed_gemini_test_credential(client.app.state.settings)
        yield client


def register_user(client: TestClient, label: str) -> tuple[dict[str, object], dict[str, str]]:
    return create_verified_test_user(client, label)


def create_prompt_version(
    client: TestClient,
    headers: dict[str, str],
    *,
    provider: str = "gemini",
    model: str = "gemini-3.5-flash-lite",
) -> tuple[dict[str, object], dict[str, object]]:
    scenario = next(
        (
            kind
            for kind in ("error", "timeout", "crash")
            if model.startswith("deterministic-" + kind)
        ),
        None,
    )
    template = (f"[test-{scenario}] " if scenario else "") + "Hello {{name}}."
    if model.startswith("deterministic-"):
        model = "gemini-3.5-flash-lite"
    project_response = seed_owned_project(
        client, headers, {"name": "Run Workspace", "key": f"run-{uuid4().hex}"}
    )
    project = project_response
    prompt_response = client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "key": "greeting",
            "name": "Greeting",
            "template_body": template,
            "model_config": {
                "provider": provider,
                "model": model,
                "temperature": 0,
                "max_output_tokens": 100,
            },
            "commit_message": "Initial",
        },
    )
    assert prompt_response.status_code == 201
    return project, prompt_response.json()["latest_version"]


@pytest.mark.database
def test_gemini_run_uses_active_encrypted_key_and_persists_usage(
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    observed: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            observed["api_key"] = self.headers.get("x-goog-api-key")
            body = json.dumps(
                {
                    "candidates": [{"content": {"parts": [{"text": "Live Gemini output"}]}}],
                    "usageMetadata": {
                        "promptTokenCount": 7,
                        "candidatesTokenCount": 3,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    model = "gemini-3.5-flash-lite"
    with psycopg.connect(seeded_database_url) as connection:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO provider_keys (provider, alias, encrypted_secret, created_by)
               VALUES ('gemini', %s, %s, %s)""",
            (
                f"integration-{uuid4().hex}",
                encrypt_provider_secret(
                    "integration-gemini-secret",
                    test_settings.resolved_provider_encryption_key,
                ),
                admin_id,
            ),
        )
        connection.commit()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "gemini_api_base_url": f"http://127.0.0.1:{server.server_port}/v1beta",
        }
    )
    try:
        with TestClient(create_app(settings)) as client:

            _, headers = register_user(client, "gemini-owner")
            _, version = create_prompt_version(client, headers, provider="gemini", model=model)
            response = client.post(
                "/api/v1/runs",
                headers=headers,
                json={"version_id": version["id"], "variables": {"name": "Jobin"}},
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status_code == 201, response.text
    run = response.json()
    assert run["provider"] == "gemini"
    assert run["output_text"] == "Live Gemini output"
    assert run["prompt_tokens"] == 7
    assert run["completion_tokens"] == 3
    assert Decimal(run["cost"]) == 0
    assert observed["api_key"] == "integration-gemini-secret"


@pytest.mark.database
def test_paid_gemini_configuration_is_rejected_before_provider_call(
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    provider_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            nonlocal provider_calls
            provider_calls += 1
            body = json.dumps(
                {
                    "candidates": [{"content": {"parts": [{"text": "Paid output"}]}}],
                    "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    model = "gemini-3.5-flash-lite"
    with psycopg.connect(seeded_database_url) as connection:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO provider_keys (provider, alias, encrypted_secret, created_by) "
            "VALUES ('gemini', %s, %s, %s)",
            (
                f"budget-{uuid4().hex}",
                encrypt_provider_secret(
                    "budget-gemini-secret",
                    test_settings.resolved_provider_encryption_key,
                ),
                admin_id,
            ),
        )
        connection.execute(
            "INSERT INTO model_pricing (provider, model, input_price_per_million, "
            "output_price_per_million, effective_from, created_by) "
            "VALUES ('gemini', %s, 1, 2, '2026-01-01T00:00:00Z', %s)",
            (model, admin_id),
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "gemini_api_base_url": f"http://127.0.0.1:{server.server_port}/v1beta",
        }
    )
    try:
        with TestClient(create_app(settings)) as client:

            user, headers = register_user(client, "gemini-budget-owner")
            _, version = create_prompt_version(client, headers, provider="gemini", model=model)
            with psycopg.connect(seeded_database_url) as connection:
                connection.execute(
                    "INSERT INTO spend_limits (user_id, monthly_limit) VALUES (%s, 0)",
                    (user["id"],),
                )
            response = client.post(
                "/api/v1/runs",
                headers={**headers, "Idempotency-Key": "gemini-budget-request-0001"},
                json={"version_id": version["id"], "variables": {"name": "Jobin"}},
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status_code == 409
    assert response.json()["code"] == "model_not_free"
    assert provider_calls == 0
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "UPDATE model_pricing SET effective_to=clock_timestamp() "
            "WHERE provider='gemini' AND model=%s AND effective_to IS NULL "
            "AND input_price_per_million>0",
            (model,),
        )


@pytest.mark.database
def test_duplicate_idempotency_key_returns_one_persisted_gemini_run(
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    provider_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            nonlocal provider_calls
            provider_calls += 1
            body = json.dumps(
                {
                    "candidates": [{"content": {"parts": [{"text": "One output"}]}}],
                    "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    model = "gemini-3.5-flash-lite"
    with psycopg.connect(seeded_database_url) as connection:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO provider_keys (provider, alias, encrypted_secret, created_by) "
            "VALUES ('gemini', %s, %s, %s)",
            (
                f"idempotency-{uuid4().hex}",
                encrypt_provider_secret(
                    "idempotency-gemini-secret",
                    test_settings.resolved_provider_encryption_key,
                ),
                admin_id,
            ),
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "gemini_api_base_url": f"http://127.0.0.1:{server.server_port}/v1beta",
        }
    )
    try:
        with TestClient(create_app(settings)) as client:

            _, headers = register_user(client, "gemini-idempotency-owner")
            _, version = create_prompt_version(client, headers, provider="gemini", model=model)
            request_headers = {
                **headers,
                "Idempotency-Key": "gemini-idempotency-request-0001",
            }
            payload = {"version_id": version["id"], "variables": {"name": "Jobin"}}
            first = client.post("/api/v1/runs", headers=request_headers, json=payload)
            duplicate = client.post("/api/v1/runs", headers=request_headers, json=payload)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first.status_code == duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]
    assert provider_calls == 1


@pytest.mark.database
def test_concurrent_duplicate_run_is_not_executed_twice(
    run_client: TestClient,
    seeded_database_url: str,
) -> None:
    model = f"deterministic-delay-{uuid4().hex}"
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "INSERT INTO model_pricing (provider, model, input_price_per_million, "
            "output_price_per_million, effective_from) "
            "VALUES ('gemini', %s, 1, 1, '2026-01-01T00:00:00Z')",
            (model,),
        )
    _, headers = register_user(run_client, "concurrent-idempotency-owner")
    _, version = create_prompt_version(run_client, headers, model=model)
    request_headers = {
        **headers,
        "Idempotency-Key": "concurrent-idempotency-request-0001",
    }
    payload = {"version_id": version["id"], "variables": {"name": "Jobin"}}

    def execute() -> tuple[int, dict[str, object]]:
        response = run_client.post("/api/v1/runs", headers=request_headers, json=payload)
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: execute(), range(2)))

    assert sorted(status for status, _ in results) == [201, 409]
    rejected = next(body for status, body in results if status == 409)
    assert rejected["code"] == "execution_in_progress"
    with psycopg.connect(seeded_database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM run_context WHERE version_id = %s",
            (version["id"],),
        ).fetchone() == (1,)


@pytest.mark.database
def test_uncertain_provider_failure_keeps_reservation_and_cannot_be_replayed(
    test_settings: Settings,
    seeded_database_url: str,
) -> None:
    provider_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            nonlocal provider_calls
            provider_calls += 1
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    model = "gemini-3.5-flash-lite"
    with psycopg.connect(seeded_database_url) as connection:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO provider_keys (provider, alias, encrypted_secret, created_by) "
            "VALUES ('gemini', %s, %s, %s)",
            (
                f"uncertain-{uuid4().hex}",
                encrypt_provider_secret(
                    "uncertain-gemini-secret",
                    test_settings.resolved_provider_encryption_key,
                ),
                admin_id,
            ),
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "gemini_api_base_url": f"http://127.0.0.1:{server.server_port}/v1beta",
        }
    )
    key = "gemini-uncertain-request-0001"
    try:
        with TestClient(create_app(settings)) as client:

            user, headers = register_user(client, "gemini-uncertain-owner")
            _, version = create_prompt_version(client, headers, provider="gemini", model=model)
            request_headers = {**headers, "Idempotency-Key": key}
            payload = {"version_id": version["id"], "variables": {"name": "Jobin"}}
            first = client.post("/api/v1/runs", headers=request_headers, json=payload)
            replay = client.post("/api/v1/runs", headers=request_headers, json=payload)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert first.status_code == 502
    assert first.json()["code"] == "provider_error"
    assert replay.status_code == 409
    assert replay.json()["code"] == "execution_outcome_unknown"
    assert provider_calls == 1
    with psycopg.connect(seeded_database_url) as connection:
        reservation = connection.execute(
            "SELECT status, estimated_cost, actual_cost FROM reservation_context "
            "WHERE user_id = %s AND idempotency_key = %s",
            (user["id"], key),
        ).fetchone()
    assert reservation is not None
    assert reservation[0] == "uncertain"
    assert reservation[1] == 0
    assert reservation[2] is None


@pytest.mark.database
def test_run_execution_persists_precise_ledger_and_scopes_reads(
    run_client: TestClient,
    seeded_database_url: str,
) -> None:
    user, headers = register_user(run_client, "run-owner")
    _, outsider_headers = register_user(run_client, "run-outsider")
    project, version = create_prompt_version(run_client, headers)

    request_id = "r" * 128
    executed = run_client.post(
        "/api/v1/runs",
        headers={**headers, "X-Request-ID": request_id},
        json={"version_id": version["id"], "variables": {"name": "Jobin"}},
    )

    assert executed.status_code == 201
    run = executed.json()
    assert run["user_id"] == user["id"]
    assert run["project_id"] == project["id"]
    assert run["version_id"] == version["id"]
    assert run["status"] == "completed"
    assert run["provider"] == "gemini"
    assert run["model"] == "gemini-3.5-flash-lite"
    assert run["input_variables"] == {"name": "Jobin"}
    assert run["output_text"] == "Simulated Gemini response: Hello Jobin."
    assert run["prompt_tokens"] == 3
    assert run["completion_tokens"] == 6
    assert run["latency_ms"] == 25
    assert Decimal(run["cost"]) == Decimal("0")
    assert run["error_code"] is None
    with psycopg.connect(seeded_database_url) as connection:
        stored_request_id = connection.execute(
            "SELECT request_id FROM run_context WHERE id = %s", (run["id"],)
        ).fetchone()
    assert stored_request_id == (request_id,)

    detail = run_client.get(f"/api/v1/runs/{run['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json() == run

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={
            "project_id": project["id"],
            "status": "completed",
            "model": "gemini-3.5-flash-lite",
        },
    )
    assert page.status_code == 200
    assert run["id"] in {item["id"] for item in page.json()["items"]}

    hidden = run_client.get(f"/api/v1/runs/{run['id']}", headers=outsider_headers)
    unknown = run_client.get(f"/api/v1/runs/{uuid4()}", headers=outsider_headers)
    outsider_page = run_client.get("/api/v1/runs", headers=outsider_headers)
    assert hidden.status_code == unknown.status_code == 404
    assert run["id"] not in {item["id"] for item in outsider_page.json()["items"]}


@pytest.mark.database
def test_run_rejects_variable_mismatch_without_calling_provider(
    run_client: TestClient,
) -> None:
    _, headers = register_user(run_client, "variable-owner")
    _, version = create_prompt_version(run_client, headers)

    for variables in ({}, {"name": "Jobin", "admin": "true"}):
        response = run_client.post(
            "/api/v1/runs",
            headers=headers,
            json={"version_id": version["id"], "variables": variables},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_variables"

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"version_id": version["id"]},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 0


@pytest.mark.database
def test_run_rejects_oversized_variable_payload_without_ledger_row(
    run_client: TestClient,
) -> None:
    _, headers = register_user(run_client, "oversized-variable-owner")
    _, version = create_prompt_version(run_client, headers)

    response = run_client.post(
        "/api/v1/runs",
        headers=headers,
        json={
            "version_id": version["id"],
            "variables": {"name": "x" * 60_000, "other": "y" * 60_000},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"version_id": version["id"]},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 0


@pytest.mark.database
def test_run_list_truncates_output_but_detail_keeps_full_ledger_value(
    run_client: TestClient,
) -> None:
    _, headers = register_user(run_client, "run-output-owner")
    _, version = create_prompt_version(run_client, headers)
    response = run_client.post(
        "/api/v1/runs",
        headers=headers,
        json={"version_id": version["id"], "variables": {"name": "x" * 3_000}},
    )
    assert response.status_code == 201
    full_output = response.json()["output_text"]
    assert len(full_output) > 3_000

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"version_id": version["id"]},
    )
    detail = run_client.get(f"/api/v1/runs/{response.json()['id']}", headers=headers)
    assert page.status_code == detail.status_code == 200
    assert len(page.json()["items"][0]["output_text"]) == 2_000
    assert detail.json()["output_text"] == full_output


@pytest.mark.database
def test_run_search_filters_the_full_scoped_ledger_before_pagination(
    run_client: TestClient,
) -> None:
    _, headers = register_user(run_client, "search-owner")
    _, version = create_prompt_version(run_client, headers)
    created_ids: list[str] = []
    for index in range(3):
        response = run_client.post(
            "/api/v1/runs",
            headers=headers,
            json={"version_id": version["id"], "variables": {"name": f"Search {index}"}},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    response = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"search": created_ids[-1][:12], "page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == created_ids[-1]

    wildcard = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"search": "%", "page": 1, "page_size": 10},
    )
    assert wildcard.status_code == 200
    assert wildcard.json()["total"] == 0


@pytest.mark.database
@pytest.mark.parametrize(
    ("model", "status_code", "error_code"),
    [
        ("deterministic-error", 502, "provider_error"),
        ("deterministic-timeout", 504, "provider_timeout"),
        ("deterministic-crash", 502, "provider_error"),
    ],
)
def test_provider_failures_return_normalized_errors_and_remain_in_ledger(
    run_client: TestClient,
    seeded_database_url: str,
    model: str,
    status_code: int,
    error_code: str,
) -> None:
    model = f"{model}-{uuid4().hex}"
    _, headers = register_user(run_client, f"{model}-owner")
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """
            INSERT INTO model_pricing (
                provider, model, input_price_per_million,
                output_price_per_million, effective_from
            ) VALUES ('gemini', %s, 1, 2, '2026-01-01T00:00:00Z')
            """,
            (model,),
        )
    _, version = create_prompt_version(run_client, headers, model=model)

    response = run_client.post(
        "/api/v1/runs",
        headers=headers,
        json={"version_id": version["id"], "variables": {"name": "Jobin"}},
    )
    assert response.status_code == status_code
    assert response.json()["code"] == error_code

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"version_id": version["id"]},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    recorded = page.json()["items"][0]
    assert recorded["status"] == "failed"
    assert recorded["error_code"] == error_code
    assert Decimal(recorded["cost"]) == 0
    assert recorded["output_text"] is None


@pytest.mark.database
def test_free_gemini_executes_with_zero_budget_without_charge(
    run_client: TestClient,
    seeded_database_url: str,
) -> None:
    user, headers = register_user(run_client, "budget-owner")
    project, version = create_prompt_version(run_client, headers)
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """
            INSERT INTO spend_limits (user_id, monthly_limit, timezone, created_by)
            VALUES (%s, 0, 'UTC', %s)
            """,
            (user["id"], user["id"]),
        )

    response = run_client.post(
        "/api/v1/runs",
        headers=headers,
        json={"version_id": version["id"], "variables": {"name": "Jobin"}},
    )
    assert response.status_code == 201

    page = run_client.get(
        "/api/v1/runs",
        headers=headers,
        params={"project_id": project["id"]},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1
    blocked = page.json()["items"][0]
    assert blocked["status"] == "completed"
    assert blocked["error_code"] is None
    assert Decimal(blocked["cost"]) == 0
    assert blocked["output_text"] is not None

    dashboard = run_client.get("/api/v1/dashboard/me", headers=headers)
    assert dashboard.status_code == 200
    summary = dashboard.json()
    assert summary["project_count"] == 1
    assert summary["prompt_count"] == 1
    assert summary["run_count"] == 1
    assert summary["completed_run_count"] == 1
    assert summary["blocked_run_count"] == 0
    assert Decimal(summary["monthly_spend"]) == 0
    assert Decimal(summary["monthly_budget"]) == 0
    assert summary["recent_runs"][0]["id"] == blocked["id"]


@pytest.mark.database
def test_unsupported_model_is_rejected_before_version_creation(run_client: TestClient) -> None:
    _, headers = register_user(run_client, "unsupported-model-owner")
    project = seed_owned_project(
        run_client, headers, {"name": "Unsupported", "key": "unsupported-" + uuid4().hex}
    )
    response = run_client.post(
        f"/api/v1/projects/{project['id']}/prompts",
        headers=headers,
        json={
            "name": "Rejected",
            "key": "rejected",
            "template_body": "Hello",
            "commit_message": "Rejected",
            "model_config": {
                "provider": "gemini",
                "model": "not-a-reviewed-free-model",
                "max_output_tokens": 100,
            },
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "model_not_available"


@pytest.mark.database
def test_membership_is_revalidated_after_provider_execution(
    run_client: TestClient,
    seeded_database_url: str,
) -> None:
    member, member_headers = register_user(run_client, "delayed-member")
    _, owner_headers = register_user(run_client, "delayed-owner")
    model = f"deterministic-delay-{uuid4().hex}"
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """
            INSERT INTO model_pricing (
                provider, model, input_price_per_million,
                output_price_per_million, effective_from
            ) VALUES ('gemini', %s, 1, 2, '2026-01-01T00:00:00Z')
            """,
            (model,),
        )
    project, version = create_prompt_version(run_client, owner_headers, model=model)
    added = run_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert added.status_code == 201
    accept_invitation(run_client, str(member["email"]), member_headers)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            run_client.post,
            "/api/v1/runs",
            headers=member_headers,
            json={"version_id": version["id"], "variables": {"name": "Jobin"}},
        )
        time.sleep(0.05)
        removed = run_client.delete(
            f"/api/v1/projects/{project['id']}/members/{member['id']}",
            headers=owner_headers,
        )
        response = pending.result(timeout=2)

    assert removed.status_code == 204
    assert response.status_code == 404
    page = run_client.get(
        "/api/v1/runs",
        headers=owner_headers,
        params={"project_id": project["id"]},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 0


@pytest.mark.database
def test_provider_wait_does_not_hold_the_only_database_connection(
    single_connection_run_client: TestClient,
    seeded_database_url: str,
) -> None:
    client = single_connection_run_client
    _, headers = register_user(client, "pool-release-owner")
    model = f"deterministic-delay-{uuid4().hex}"
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            """
            INSERT INTO model_pricing (
                provider, model, input_price_per_million,
                output_price_per_million, effective_from
            ) VALUES ('gemini', %s, 1, 2, '2026-01-01T00:00:00Z')
            """,
            (model,),
        )
    _, version = create_prompt_version(client, headers, model=model)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            client.post,
            "/api/v1/runs",
            headers=headers,
            json={"version_id": version["id"], "variables": {"name": "Jobin"}},
        )
        time.sleep(0.05)
        projects = client.get("/api/v1/projects", headers=headers)
        completed = pending.result(timeout=2)

    assert projects.status_code == 200
    assert completed.status_code == 201


@pytest.mark.database
def test_run_reads_cover_member_removed_owner_and_admin_scopes(
    run_client: TestClient,
) -> None:
    member, member_headers = register_user(run_client, "scope-member")
    _, owner_headers = register_user(run_client, "scope-owner")
    project, version = create_prompt_version(run_client, owner_headers)
    added = run_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert added.status_code == 201
    accept_invitation(run_client, str(member["email"]), member_headers)

    owner_run_response = run_client.post(
        "/api/v1/runs",
        headers=owner_headers,
        json={"version_id": version["id"], "variables": {"name": "Owner"}},
    )
    member_run_response = run_client.post(
        "/api/v1/runs",
        headers=member_headers,
        json={"version_id": version["id"], "variables": {"name": "Member"}},
    )
    assert owner_run_response.status_code == member_run_response.status_code == 201
    owner_run = owner_run_response.json()
    member_run = member_run_response.json()

    assert (
        run_client.get(f"/api/v1/runs/{owner_run['id']}", headers=member_headers).status_code == 200
    )
    removed = run_client.delete(
        f"/api/v1/projects/{project['id']}/members/{member['id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 204
    assert (
        run_client.get(f"/api/v1/runs/{owner_run['id']}", headers=member_headers).status_code == 404
    )
    assert (
        run_client.get(f"/api/v1/runs/{member_run['id']}", headers=member_headers).status_code
        == 200
    )

    admin_session = run_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
    )
    assert admin_session.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_session.json()['access_token']}"}
    assert (
        run_client.get(f"/api/v1/runs/{owner_run['id']}", headers=admin_headers).status_code == 200
    )
    admin_page = run_client.get(
        "/api/v1/runs",
        headers=admin_headers,
        params={"project_id": project["id"]},
    )
    assert admin_page.status_code == 200
    assert {item["id"] for item in admin_page.json()["items"]} == {
        owner_run["id"],
        member_run["id"],
    }


@pytest.mark.database
def test_run_and_dashboard_routes_require_auth_and_reject_invalid_filters(
    run_client: TestClient,
) -> None:
    _, headers = register_user(run_client, "filter-owner")
    assert run_client.get("/api/v1/runs").status_code == 401
    assert run_client.get("/api/v1/dashboard/me").status_code == 401
    assert run_client.post("/api/v1/runs", json={}).status_code == 401

    invalid_run_filter = run_client.get(
        "/api/v1/runs", headers=headers, params={"unsupported": "value"}
    )
    assert invalid_run_filter.status_code == 400
    assert invalid_run_filter.json()["code"] == "invalid_filter"
    for month in ("2026-13", "0000-01", "9999-12"):
        invalid_month = run_client.get(
            "/api/v1/dashboard/me", headers=headers, params={"month": month}
        )
        assert invalid_month.status_code == 400
        assert invalid_month.json()["code"] == "invalid_filter"

"""Release validation gates use isolated PostgreSQL and Gemini doubles only."""

from uuid import uuid4

import psycopg
import pytest
from api.tests.integration.test_evaluations import evaluation_context as context_fixture
from tests.auth_support import create_verified_test_user
from tests.provider_support import SimulatedGemini

release_context = context_fixture


@pytest.fixture(autouse=True)
def simulated_generation(monkeypatch):
    monkeypatch.setattr(
        "api.app.services.playground.get_provider", lambda *args, **kwargs: SimulatedGemini()
    )


def validate(context, *, version=None, environment="prod", suite_changes=None):
    client, headers, _, setup, _, _ = context
    suite = {key: value for key, value in setup.items() if key not in ("version_ids", "preset")}
    suite.update(suite_changes or {})
    payload = {
        "id": str(uuid4()),
        "version_id": version or setup["version_ids"][1],
        "environment": environment,
        "suite": suite,
    }
    response = client.post("/api/v1/deployments/validations", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    result = client.get(f"/api/v1/deployments/validations/{payload['id']}", headers=headers)
    assert result.status_code == 200, result.text
    return payload, result.json()


def request(context, payload):
    client, headers, *_ = context
    return client.post(
        "/api/v1/deployments",
        headers=headers,
        json={
            "version_id": payload["version_id"],
            "environment": payload["environment"],
            "validation_id": payload["id"],
            "request_note": "Validated release",
        },
    )


@pytest.mark.database
def test_release_runs_exact_version_then_attaches_report_to_request(release_context):
    payload, report = validate(release_context)
    assert report["status"] == "passed", report
    assert report["evaluation"]["results"][0]["weighted_score"] == 96
    created = request(release_context, payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    client, headers, prompt_id, *_ = release_context
    detail = client.get(f"/api/v1/deployments/{created.json()['id']}", headers=headers).json()
    assert detail["validation"]["id"] == report["id"]
    assert client.get(f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers).json() == []
    # Release-only tests never replace the saved comparison suite.
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/evaluation-setup", headers=headers).json()[
            "configuration"
        ]
        is None
    )


@pytest.mark.database
def test_no_validation_and_mismatched_environment_cannot_activate(release_context):
    client, headers, _, setup, *_ = release_context
    response = client.post(
        "/api/v1/deployments",
        headers=headers,
        json={"version_id": setup["version_ids"][1], "environment": "dev"},
    )
    assert response.status_code == 409
    payload, _ = validate(release_context)
    payload["environment"] = "dev"
    assert request(release_context, payload).status_code == 409


@pytest.mark.database
def test_low_scores_and_required_checks_block_release(release_context):
    weak, report = validate(release_context, version=release_context[3]["version_ids"][0])
    assert report["status"] == "blocked"
    assert request(release_context, weak).status_code == 409
    invalid, report = validate(
        release_context,
        suite_changes={
            "requirements": {"valid_json": True, "max_words": 1, "required_fields": ["answer"]}
        },
    )
    assert report["status"] == "blocked"
    assert any(not c["passed"] for c in report["evaluation"]["results"][0]["checks"])
    assert request(release_context, invalid).status_code == 409


@pytest.mark.database
def test_retry_is_idempotent_and_cross_member_read_is_hidden(release_context):
    client, headers, *_ = release_context
    payload, report = validate(release_context)
    repeated = client.post("/api/v1/deployments/validations", headers=headers, json=payload)
    assert repeated.status_code == 202
    assert repeated.json()["evaluation"]["id"] == report["evaluation"]["id"]
    altered = {**payload, "environment": "staging"}
    assert (
        client.post("/api/v1/deployments/validations", headers=headers, json=altered).status_code
        == 409
    )
    _, outsider = create_verified_test_user(client, "release-outsider")
    assert (
        client.get(f"/api/v1/deployments/validations/{report['id']}", headers=outsider).status_code
        == 404
    )


@pytest.mark.database
def test_changed_saved_suite_invalidates_previous_pass(release_context):
    client, headers, prompt_id, setup, *_ = release_context
    payload, report = validate(release_context)
    assert report["status"] == "passed"
    saved = client.put(f"/api/v1/prompts/{prompt_id}/evaluation-setup", headers=headers, json=setup)
    assert saved.status_code == 200, saved.text
    current = client.get(f"/api/v1/deployments/validations/{report['id']}", headers=headers)
    assert current.json()["status"] == "stale"
    assert request(release_context, payload).status_code == 409
    saved_payload = {"id": str(uuid4()), "version_id": payload["version_id"], "environment": "prod"}
    started = client.post("/api/v1/deployments/validations", headers=headers, json=saved_payload)
    assert started.status_code == 202, started.text
    assert (
        client.get(
            f"/api/v1/deployments/validations/{saved_payload['id']}", headers=headers
        ).json()["status"]
        == "passed"
    )


@pytest.mark.database
def test_active_release_changes_make_parallel_evidence_stale(release_context):
    first, _ = validate(release_context, environment="staging")
    second, _ = validate(release_context, environment="staging")
    assert request(release_context, first).status_code == 201
    assert request(release_context, second).status_code == 409


@pytest.mark.database
def test_fix_is_only_a_draft_and_must_be_saved_and_tested(release_context):
    client, headers, prompt_id, setup, *_ = release_context
    payload, report = validate(release_context, version=setup["version_ids"][0])
    assert report["status"] == "blocked"
    before = client.get(f"/api/v1/prompts/{prompt_id}/versions", headers=headers).json()["total"]
    draft = client.post(
        f"/api/v1/deployments/validations/{payload['id']}/suggest-fix", headers=headers
    )
    assert draft.status_code == 200, draft.text
    assert "{{topic}}" in draft.json()["template"]
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/versions", headers=headers).json()["total"]
        == before
    )
    assert request(release_context, payload).status_code == 409


@pytest.mark.database
def test_missing_tests_and_quota_fail_closed(release_context):
    client, headers, _, setup, gemini, _ = release_context
    payload = {"id": str(uuid4()), "version_id": setup["version_ids"][1], "environment": "prod"}
    response = client.post("/api/v1/deployments/validations", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "blocked"
    gemini.quota = True
    payload, report = validate(release_context)
    assert report["status"] == "blocked"
    assert report["evaluation"]["status"] == "failed"
    assert request(release_context, payload).status_code == 409


@pytest.mark.database
def test_database_entry_point_cannot_bypass_validation(release_context, seeded_database_url):
    _, _, _, setup, _, user = release_context
    with (
        psycopg.connect(seeded_database_url) as connection,
        pytest.raises(psycopg.errors.RaiseException, match="release_validation"),
    ):
        connection.execute(
            "SELECT request_deployment(%s,'dev',%s)", (setup["version_ids"][1], user["id"])
        )


def reviewer(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.database
def test_admin_review_rechecks_staleness_and_requester_can_refresh(release_context):
    client, headers, prompt_id, setup, *_ = release_context
    payload, _ = validate(release_context)
    created = request(release_context, payload).json()
    root = reviewer(client)
    # Operational Admin is not a project member but can read the attached report.
    account, _ = create_verified_test_user(client, "release-reviewer")
    assert (
        client.patch(
            f"/api/v1/admin/users/{account['id']}", headers=root, json={"role": "admin"}
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": account["email"], "password": "CorrectHorse2026!"}
    )
    admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
    detail = client.get(f"/api/v1/admin/deployments/{created['id']}", headers=admin)
    assert detail.status_code == 200, detail.text
    assert detail.json()["validation"]["status"] == "passed"
    assert (
        client.put(
            f"/api/v1/prompts/{prompt_id}/evaluation-setup", headers=headers, json=setup
        ).status_code
        == 200
    )
    blocked = client.post(
        f"/api/v1/admin/deployments/{created['id']}/approve", headers=admin, json={}
    )
    assert blocked.status_code == 409, blocked.text
    refreshed, _ = validate(release_context)
    attach = client.post(
        f"/api/v1/deployments/{created['id']}/validation",
        headers=headers,
        json={"validation_id": refreshed["id"]},
    )
    assert attach.status_code == 200, attach.text
    approved = client.post(
        f"/api/v1/admin/deployments/{created['id']}/approve", headers=admin, json={}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "active"
    repeated = client.post(
        f"/api/v1/admin/deployments/{created['id']}/approve", headers=admin, json={}
    )
    assert repeated.status_code == 409


@pytest.mark.database
def test_input_contract_change_is_blocked_before_gemini(release_context):
    client, headers, prompt_id, setup, gemini, _ = release_context
    initial, _ = validate(release_context, environment="staging")
    assert request(release_context, initial).status_code == 201
    current = client.get(f"/api/v1/versions/{initial['version_id']}", headers=headers).json()
    changed = client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "parent_version_id": initial["version_id"],
            "template_body": "STRONG Answer {{new_input}}.",
            "model_config": current["model_config"],
            "commit_message": "Break input contract",
        },
    )
    assert changed.status_code == 201, changed.text
    before = len(gemini.calls)
    payload, report = validate(
        release_context,
        version=changed.json()["id"],
        environment="staging",
        suite_changes={"cases": [{"name": "Input check", "variables": {"new_input": "Example"}}]},
    )
    assert report["status"] == "blocked"
    assert report["evaluation"] is None
    assert len(gemini.calls) == before
    assert request(release_context, payload).status_code == 409


@pytest.mark.database
def test_release_history_does_not_block_project_deletion(release_context):
    client, headers, prompt_id, *_ = release_context
    payload, _ = validate(release_context, environment="staging")
    created = request(release_context, payload)
    assert created.status_code == 201, created.text
    project_id = created.json()["project_id"]
    deleted = client.delete(f"/api/v1/projects/{project_id}", headers=reviewer(client))
    assert deleted.status_code == 204, deleted.text
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers).status_code == 404
    )


@pytest.mark.database
def test_expired_report_cannot_release(release_context, seeded_database_url):
    client, headers, *_ = release_context
    payload, _ = validate(release_context)
    with psycopg.connect(seeded_database_url) as connection:
        connection.execute(
            "UPDATE release_validations SET created_at=created_at-INTERVAL '25 hours' WHERE id=%s",
            (payload["id"],),
        )
    report = client.get(f"/api/v1/deployments/validations/{payload['id']}", headers=headers)
    assert report.json()["status"] == "stale"
    assert request(release_context, payload).status_code == 409


@pytest.mark.database
def test_application_role_cannot_bypass_release_boundary(seeded_database_url):
    with psycopg.connect(seeded_database_url) as connection:
        privileges = connection.execute("""SELECT
            has_function_privilege('promptvault_app',
                'request_deployment(uuid,deployment_environment,uuid,text,uuid)', 'EXECUTE'),
            has_function_privilege('promptvault_app',
                'request_deployment_without_validation(uuid,deployment_environment,uuid,text)',
                'EXECUTE'),
            has_function_privilege('promptvault_app',
                'review_production_deployment_without_validation(uuid,uuid,boolean,text)',
                'EXECUTE'),
            has_table_privilege('promptvault_app','release_validations','UPDATE')""").fetchone()
        assert privileges == (True, False, False, False)

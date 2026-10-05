import http.client
import json
import os
import subprocess
import sys
from pathlib import Path

from api.app.config import Settings
from api.app.main import create_app
from api.app.openapi import export_openapi

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_export_openapi_writes_deterministic_frontend_contract(
    tmp_path: Path,
    test_settings: Settings,
) -> None:
    output = tmp_path / "openapi.json"
    app = create_app(test_settings)

    export_openapi(app, output)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "PromptVault API"
    assert "/health" in document["paths"]
    assert "/ready" in document["paths"]
    assert "/api/v1/auth/register" in document["paths"]
    assert "/api/v1/auth/login" in document["paths"]
    assert "/api/v1/auth/me" in document["paths"]
    assert "/api/v1/auth/password-reset" in document["paths"]
    assert "/api/v1/auth/password-reset/confirm" in document["paths"]
    assert "/api/v1/projects" in document["paths"]
    assert "/api/v1/projects/{project_id}" in document["paths"]
    assert "/api/v1/projects/{project_id}/members" in document["paths"]
    assert "/api/v1/projects/{project_id}/members/{user_id}" in document["paths"]
    assert "/api/v1/projects/{project_id}/prompts" in document["paths"]
    assert "/api/v1/prompts/{prompt_id}" in document["paths"]
    assert "/api/v1/prompts/{prompt_id}/versions" in document["paths"]
    assert "/api/v1/versions/{version_id}" in document["paths"]
    assert "/api/v1/versions/{version_id}/diff" in document["paths"]
    assert "/api/v1/versions/{version_id}/lineage" in document["paths"]
    assert "/api/v1/runs" in document["paths"]
    assert "/api/v1/runs/{run_id}" in document["paths"]
    assert "/api/v1/dashboard/me" in document["paths"]
    assert "/api/v1/deployments" in document["paths"]
    assert "/api/v1/deployments/{deployment_id}/cancel" in document["paths"]
    assert "/api/v1/admin/deployments/pending" in document["paths"]
    assert "/api/v1/admin/deployments/{deployment_id}/approve" in document["paths"]
    assert "/api/v1/admin/prompts/{prompt_id}/rollback" in document["paths"]
    assert "/api/v1/api-tokens" in document["paths"]
    assert "/api/v1/api-tokens/{token_id}" in document["paths"]
    assert "/serve/v1/prompts/{key}" in document["paths"]
    assert "/api/v1/admin/dashboard" in document["paths"]
    assert "/api/v1/admin/users" in document["paths"]
    assert "/api/v1/admin/users/{user_id}" in document["paths"]
    assert "/api/v1/admin/budgets" in document["paths"]
    assert "/api/v1/admin/budgets/{budget_id}" in document["paths"]
    assert "/api/v1/admin/provider-keys" in document["paths"]
    assert "/api/v1/admin/provider-keys/{key_id}" in document["paths"]
    assert "/api/v1/admin/model-pricing" in document["paths"]
    assert "/api/v1/admin/runs" in document["paths"]
    assert "/api/v1/admin/audit" in document["paths"]
    assert "/api/v1/admin/maintenance" in document["paths"]
    assert "/api/v1/admin/maintenance/refresh-views" in document["paths"]
    assert "/api/v1/admin/maintenance/create-next-partition" in document["paths"]
    project_list_responses = document["paths"]["/api/v1/projects"]["get"]["responses"]
    assert {"200", "400", "401", "403", "422"}.issubset(project_list_responses)
    for status_code in ("400", "401", "403", "422"):
        schema = project_list_responses[status_code]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}
    project_create_responses = document["paths"]["/api/v1/projects"]["post"]["responses"]
    assert {"201", "401", "403", "409", "413", "422"}.issubset(project_create_responses)
    assert project_create_responses["413"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    assert project_create_responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    run_create_responses = document["paths"]["/api/v1/runs"]["post"]["responses"]
    assert {"201", "401", "404", "409", "422", "502", "504"}.issubset(
        run_create_responses
    )
    for status_code in ("409", "502", "504"):
        assert run_create_responses[status_code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }
    rollback_responses = document["paths"][
        "/api/v1/admin/prompts/{prompt_id}/rollback"
    ]["post"]["responses"]
    assert "409" in rollback_responses
    assert rollback_responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    serve_responses = document["paths"]["/serve/v1/prompts/{key}"]["get"]["responses"]
    for status_code in ("200", "304"):
        assert set(serve_responses[status_code]["headers"]) == {
            "ETag",
            "Cache-Control",
            "Vary",
        }
    assert "ErrorEnvelope" in document["components"]["schemas"]
    register_fields = document["components"]["schemas"]["RegisterRequest"]["properties"]
    assert set(register_fields) == {"email", "password", "display_name"}
    first_render = output.read_text(encoding="utf-8")
    assert "password_hash" not in first_render
    assert "HTTPBearer" in document["components"]["securitySchemes"]
    export_openapi(app, output)
    assert output.read_text(encoding="utf-8") == first_render
    assert first_render.endswith("\n")


def test_openapi_export_script_exposes_help() -> None:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("SECRET_KEY", None)
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "export-openapi.py"), "--help"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


def test_openapi_error_descriptions_do_not_depend_on_python_reason_phrases(
    tmp_path: Path,
    test_settings: Settings,
    monkeypatch,
) -> None:
    monkeypatch.setitem(http.client.responses, 422, "Interpreter-specific wording")
    output = tmp_path / "openapi.json"

    export_openapi(create_app(test_settings), output)

    document = json.loads(output.read_text(encoding="utf-8"))
    response = document["paths"]["/api/v1/projects"]["get"]["responses"]["422"]
    assert response["description"] == "Unprocessable Content"

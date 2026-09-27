"""Delivery stack contract exercised through Docker Compose itself."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def compose_config(overrides: dict[str, str] | None = None) -> dict[str, object]:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed")
    environment = {
        **os.environ,
        "ENVIRONMENT": "development",
        "SECRET_KEY": "change-me",
        "CORS_ORIGINS": "http://localhost:5173",
        "VITE_API_URL": "http://localhost:8000",
    }
    environment.update(overrides or {})
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "verification",
            "config",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if "docker: 'compose' is not a docker command" in result.stderr:
        pytest.skip("Docker Compose plugin is not installed")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_local_stack_has_health_gated_startup_and_persistent_database() -> None:
    document = compose_config()
    services = document["services"]
    assert {"db", "migrate", "api", "web"}.issubset(services)

    assert services["db"]["healthcheck"]
    assert services["api"]["healthcheck"]
    assert services["web"]["healthcheck"]
    assert services["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"

    database_mounts = services["db"]["volumes"]
    assert any(mount["target"] == "/var/lib/postgresql/data" for mount in database_mounts)
    assert "promptvault-data" in document["volumes"]


def test_verification_profile_runs_the_backend_suite_against_disposable_database() -> None:
    services = compose_config()["services"]
    verify = services["verify"]
    assert verify["profiles"] == ["verification"]
    assert verify["environment"]["TEST_DATABASE_URL"].endswith("/promptvault_test")
    assert verify["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_uses_internal_database_address_and_non_secret_defaults() -> None:
    services = compose_config()["services"]
    database_url = services["api"]["environment"]["DATABASE_URL"]
    assert "@db:5432/" in database_url
    assert services["migrate"]["environment"]["DATABASE_URL"] == database_url
    assert services["api"]["environment"]["ENVIRONMENT"] == "development"
    assert services["api"]["environment"]["SECRET_KEY"] == "change-me"


def test_public_api_and_cors_addresses_can_be_configured() -> None:
    services = compose_config(
        {
            "CORS_ORIGINS": "https://app.example.com",
            "VITE_API_URL": "https://api.example.com",
        }
    )["services"]
    assert services["api"]["environment"]["CORS_ORIGINS"] == "https://app.example.com"
    assert services["web"]["build"]["args"]["VITE_API_URL"] == "https://api.example.com"


def test_compose_project_and_database_volume_are_checkout_isolated() -> None:
    document = compose_config({"COMPOSE_PROJECT_NAME": "promptvault-verification-example"})
    assert document["name"] == "promptvault-verification-example"
    assert document["volumes"]["promptvault-data"]["name"] == (
        "promptvault-verification-example_promptvault-data"
    )
    for service_name in ("api", "migrate", "web", "verify"):
        assert document["services"][service_name]["image"].startswith(
            "promptvault-verification-example-"
        )

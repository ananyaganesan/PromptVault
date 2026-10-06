"""Production Compose contract keeps secrets private and services isolated."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPOSITORY_ROOT / "docker-compose.production.yml"


def test_production_stack_has_tls_metrics_redis_and_restricted_runtime(
    tmp_path: Path,
) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed")
    for name in (
        "postgres_owner_password",
        "migration_database_url",
        "runtime_database_password",
        "runtime_database_url",
        "secret_key",
        "provider_encryption_key",
        "redis_password",
        "rate_limit_redis_url",
        "smtp_password",
    ):
        path = tmp_path / name
        path.write_text("test-secret")
        path.chmod(0o400)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "--profile",
            "operations",
            "config",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "DOMAIN": "promptvault.example.com",
            "SECRET_DIR": str(tmp_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    services = document["services"]
    assert {"db", "redis", "migrate", "provision", "api", "web", "caddy", "prometheus"}.issubset(services)
    assert services["api"]["environment"]["ENVIRONMENT"] == "production"
    assert services["api"]["environment"]["DATABASE_ROLE"] == "promptvault_app"
    assert services["api"]["user"] == "0:0"
    assert "setpriv --reuid=999 --regid=999 --clear-groups" in services["api"]["command"][-1]
    assert services["migrate"]["user"] == "0:0"
    assert "setpriv --reuid=999 --regid=999 --clear-groups" in services["migrate"]["command"][-1]
    assert services["provision"]["user"] == "0:0"
    assert "setpriv --reuid=999 --regid=999 --clear-groups" in services["provision"]["entrypoint"][-1]
    assert "setpriv --reuid=999 --regid=1000 --clear-groups" in services["redis"]["command"][-1]
    assert services["api"]["depends_on"]["provision"]["condition"] == "service_completed_successfully"
    assert services["api"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert "--forwarded-allow-ips='*'" in services["api"]["command"][-1]
    assert services["caddy"]["ports"]
    for service_name in ("db", "redis", "api", "web", "prometheus"):
        assert not services[service_name].get("ports")
    assert services["backup"]["profiles"] == ["operations"]

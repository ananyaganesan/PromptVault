"""Normal local startup must not switch to another database server or test data."""

import importlib.util
import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_startup", ROOT / "scripts/start-local.py"
)
startup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@localhost:55435/promptvault",
        "postgresql://user:pass@localhost:5432/promptvault_test",
        "postgresql://user:pass@localhost:5432/another_database",
        "postgresql://user:pass@example.com:5432/promptvault",
    ],
)
def test_normal_startup_rejects_alternate_database_targets(url: str) -> None:
    with pytest.raises(ValueError):
        startup.validate_database_url(url)


def test_normal_startup_reports_busy_port_instead_of_selecting_another() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="will not switch ports"):
            startup.require_free_port(port)


def test_normal_startup_can_reuse_a_port_after_the_previous_server_closes() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        with socket.create_connection(("127.0.0.1", port)) as client:
            connection, _ = listener.accept()
            connection.close()
            assert client.recv(1) == b""
    startup.require_free_port(port)


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker CLI is not installed"
)
def test_local_docker_override_reuses_pgadmin_server() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.local.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    services = json.loads(result.stdout)["services"]
    assert "db" not in services  # Its opt-in profile is not part of normal startup.
    assert (
        "@host.docker.internal:5432/promptvault"
        in services["api"]["environment"]["DATABASE_URL"]
    )
    assert (
        services["api"]["environment"]["DATABASE_URL"]
        == (services["migrate"]["environment"]["DATABASE_URL"])
    )
    assert not services["migrate"].get("depends_on")
    assert services["migrate"]["command"] == ["python", "scripts/run-migrations.py"]

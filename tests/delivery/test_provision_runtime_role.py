"""Production database-role provisioning safeguards."""

import importlib.util
import os
import stat
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "provision-production-role.py"


def load_script():
    spec = importlib.util.spec_from_file_location("promptvault_provision_role", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_role_name_must_be_a_safe_identifier() -> None:
    script = load_script()

    assert script.role_identifier("promptvault_runtime") == "promptvault_runtime"
    with pytest.raises(ValueError, match="safe PostgreSQL identifier"):
        script.role_identifier("runtime; DROP ROLE postgres")


def test_role_password_statement_quotes_identifier_and_secret() -> None:
    script = load_script()

    statement = script.role_password_statement(
        "CREATE", "promptvault_runtime", "secret'; DROP ROLE postgres; --"
    ).as_string()

    assert statement == (
        'CREATE ROLE "promptvault_runtime" LOGIN PASSWORD '
        "'secret''; DROP ROLE postgres; --'"
    )


def test_password_file_must_be_nonempty_and_private(tmp_path: Path) -> None:
    script = load_script()
    password_file = tmp_path / "password"
    password_file.write_text("runtime-secret\n")
    password_file.chmod(stat.S_IRUSR)

    assert script.read_private_secret(password_file) == "runtime-secret"

    password_file.chmod(stat.S_IRUSR | stat.S_IROTH)
    with pytest.raises(ValueError, match="owner-only permissions"):
        script.read_private_secret(password_file)


def test_password_can_be_received_from_a_root_only_secret_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    monkeypatch.setenv("RUNTIME_DATABASE_PASSWORD", "runtime-secret")

    assert script.resolve_password(None) == "runtime-secret"
    assert "RUNTIME_DATABASE_PASSWORD" not in os.environ

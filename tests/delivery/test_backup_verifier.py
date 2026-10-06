"""Safety rules for the disposable backup/restore verification drill."""

import importlib.util
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-backup.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("promptvault_verify_backup", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", ["promptvault", "promptvault_test", "db2026"])
def test_database_identifier_accepts_safe_names(value: str) -> None:
    verifier = load_verifier()

    assert verifier.database_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "9database", "prompt-vault", "promptvault;drop database postgres", "a" * 64],
)
def test_database_identifier_rejects_unsafe_names(value: str) -> None:
    verifier = load_verifier()

    with pytest.raises(ValueError, match="safe PostgreSQL identifier"):
        verifier.database_identifier(value)


def test_parse_counts_requires_every_nonnegative_counter() -> None:
    verifier = load_verifier()
    expected = {
        "schema_migrations": 16,
        "users": 2,
        "projects": 1,
        "prompts": 1,
        "prompt_versions": 5,
        "runs": 2_000,
        "deployments": 1,
        "api_tokens": 0,
        "audit_events": 4,
    }

    assert verifier.parse_counts(__import__("json").dumps(expected)) == expected

    with pytest.raises(ValueError, match="invalid database count payload"):
        verifier.parse_counts('{"users": -1}')

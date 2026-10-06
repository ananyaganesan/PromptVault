"""Release verifier provenance and redaction behavior."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-release.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("promptvault_verify_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redact_removes_runtime_jwt_database_and_json_secrets() -> None:
    verifier = load_verifier()
    raw = (
        'token="pv_live_example-secret" '
        'access_token="eyJheader.payload.signature" '
        'postgresql://promptvault:database-secret@db:5432/promptvault '
        '"password":"account-secret"'
    )
    redacted = verifier.redact(raw)
    for secret in (
        "pv_live_example-secret",
        "eyJheader.payload.signature",
        "database-secret",
        "account-secret",
    ):
        assert secret not in redacted


@pytest.mark.skipif(shutil.which("git") is None, reason="Git CLI is not installed")
def test_clean_worktree_detection_uses_committed_state(tmp_path: Path) -> None:
    verifier = load_verifier()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    assert verifier.repository_is_clean(tmp_path)
    tracked.write_text("dirty\n")
    assert not verifier.repository_is_clean(tmp_path)


def test_authoritative_verifier_exposes_no_skip_modes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--skip-build" not in result.stdout
    assert "--skip-tests" not in result.stdout

"""Initial production administrator bootstrap safeguards."""

import importlib.util
import os
import stat
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "bootstrap-production-admin.py"


def load_script():
    spec = importlib.util.spec_from_file_location("promptvault_bootstrap_admin", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_admin_password_file_must_be_private(tmp_path: Path) -> None:
    script = load_script()
    password_file = tmp_path / "password"
    password_file.write_text("UniqueProductionPassword2026!\n")
    password_file.chmod(stat.S_IRUSR)

    assert script.read_private_password(password_file) == "UniqueProductionPassword2026!"

    password_file.chmod(stat.S_IRUSR | stat.S_IROTH)
    with pytest.raises(ValueError, match="owner-only"):
        script.read_private_password(password_file)


def test_admin_password_environment_is_removed_after_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    monkeypatch.setenv("PRODUCTION_ADMIN_PASSWORD", "UniqueProductionPassword2026!")

    assert script.read_private_password(None) == "UniqueProductionPassword2026!"
    assert "PRODUCTION_ADMIN_PASSWORD" not in os.environ

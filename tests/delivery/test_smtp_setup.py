import runpy
from pathlib import Path

import pytest
from dotenv import dotenv_values

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "configure-smtp.py"


def run_setup(monkeypatch: pytest.MonkeyPatch, directory: Path, sender: str) -> int:
    namespace = runpy.run_path(str(SCRIPT))
    main = namespace["main"]
    main.__globals__["REPOSITORY_ROOT"] = directory
    answers = iter([sender, "https://app.example.com/reset-password"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: "abcd efgh ijkl mnop")
    monkeypatch.setattr("sys.argv", [str(SCRIPT)])
    return main()


def test_setup_preserves_settings_and_protects_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    env = tmp_path / ".env"
    env.write_text("# Keep this comment\nDATABASE_URL=postgresql://localhost/test\n"
                   "SECRET_KEY=test-secret\nWEB_PORT=5173\n")
    assert run_setup(monkeypatch, tmp_path, "sender@example.com") == 0
    values = dotenv_values(env)
    assert values["WEB_PORT"] == "5173"
    assert values["SMTP_PASSWORD"] == "abcdefghijklmnop"
    assert values["SMTP_USERNAME"] == values["SMTP_FROM_EMAIL"] == "sender@example.com"
    assert "# Keep this comment" in env.read_text()
    assert env.stat().st_mode & 0o777 == 0o600
    output = capsys.readouterr()
    assert "abcdefghijklmnop" not in output.out + output.err


def test_invalid_setup_leaves_env_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    env = tmp_path / ".env"
    original = "DATABASE_URL=postgresql://localhost/test\nSECRET_KEY=test-secret\n"
    env.write_text(original)
    assert run_setup(monkeypatch, tmp_path, "invalid-address") == 1
    assert env.read_text() == original

"""Production preflight rejects missing or insecure operator inputs."""

import importlib.util
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "production-preflight.py"


def load_preflight():
    assert SCRIPT.exists(), "production preflight script is missing"
    spec = importlib.util.spec_from_file_location("promptvault_production_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_secrets(directory: Path, names: set[str]) -> None:
    directory.mkdir(exist_ok=True)
    for name in names:
        secret = directory / name
        value = "https://alerts.acme.test/promptvault" if name == "alert_webhook_url" else f"secure-{name}"
        secret.write_text(value)
        secret.chmod(0o400)


def test_secure_complete_offline_configuration_passes(tmp_path: Path) -> None:
    preflight = load_preflight()
    names = preflight.required_secret_names()
    write_secrets(tmp_path, names)
    environment = {
        "DOMAIN": "vault.acme.test",
        "SMTP_HOST": "smtp.acme.test",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "mailer@acme.test",
        "SMTP_FROM_EMAIL": "mailer@acme.test",
        "RESTIC_REPOSITORY": "s3:https://objects.acme.test/promptvault",
    }

    assert preflight.validate_environment(environment) == []
    assert preflight.validate_secret_directory(tmp_path, names) == []
    assert preflight.validate_alert_webhook(tmp_path / "alert_webhook_url") == []


def test_missing_and_world_readable_secrets_are_rejected(tmp_path: Path) -> None:
    preflight = load_preflight()
    names = {"secret_key", "alert_webhook_url"}
    tmp_path.mkdir(exist_ok=True)
    insecure = tmp_path / "secret_key"
    insecure.write_text("real-secret")
    insecure.chmod(0o644)

    errors = preflight.validate_secret_directory(tmp_path, names)

    assert any("secret_key" in error and "0400 or 0600" in error for error in errors)
    assert any("alert_webhook_url" in error and "missing" in error for error in errors)


def test_secret_mode_must_be_exactly_owner_readable_or_owner_writable(tmp_path: Path) -> None:
    preflight = load_preflight()
    secret = tmp_path / "secret_key"
    secret.write_text("real-secret")
    secret.chmod(0o700)

    errors = preflight.validate_secret_directory(tmp_path, {"secret_key"})

    assert errors == ["secret secret_key must use mode 0400 or 0600"]


def test_placeholders_and_incomplete_services_are_rejected() -> None:
    preflight = load_preflight()

    errors = preflight.validate_environment({"DOMAIN": "promptvault.example.com"})

    assert any("DOMAIN" in error and "placeholder" in error for error in errors)
    assert any("SMTP_HOST" in error for error in errors)
    assert any("RESTIC_REPOSITORY" in error for error in errors)


def test_alert_webhook_requires_https_without_exposing_its_value(tmp_path: Path) -> None:
    preflight = load_preflight()
    webhook = tmp_path / "alert_webhook_url"
    webhook.write_text("http://alerts.internal.example/hook-with-secret")
    webhook.chmod(0o400)

    errors = preflight.validate_alert_webhook(webhook)

    assert errors == ["alert_webhook_url must contain an absolute HTTPS URL"]
    assert "hook-with-secret" not in errors[0]

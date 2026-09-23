import smtplib

import pytest
from api.app.config import Settings
from api.app.email import EmailDeliveryError, send_password_reset_email


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_values: tuple[str, str] | None = None
        self.messages = []
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self, **_: object) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_values = (username, password)

    def send_message(self, message: object) -> None:
        self.messages.append(message)


def test_password_reset_email_uses_configured_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr("api.app.email.smtplib.SMTP", FakeSMTP)
    settings = Settings(
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault",
        secret_key="test-secret-that-is-long-enough",
        smtp_host="smtp.example.com",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_from_email="no-reply@example.com",
        password_reset_url="https://app.example.com/reset-password?source=email",
    )

    send_password_reset_email(settings, "alex@example.com", "reset-token")

    client = FakeSMTP.instances[0]
    assert (client.host, client.port, client.timeout) == ("smtp.example.com", 587, 10)
    assert client.started_tls is True
    assert client.login_values == ("smtp-user", "smtp-password")
    message = client.messages[0]
    assert "source=email&token=reset-token" in message.get_content()


def test_password_reset_email_requires_smtp_configuration() -> None:
    settings = Settings(
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault",
        secret_key="test-secret-that-is-long-enough",
    )

    with pytest.raises(EmailDeliveryError):
        send_password_reset_email(settings, "alex@example.com", "reset-token")


def test_password_reset_email_wraps_smtp_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_connect(*_: object, **__: object) -> smtplib.SMTP:
        raise OSError("connection failed")

    monkeypatch.setattr("api.app.email.smtplib.SMTP", fail_to_connect)
    settings = Settings(
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault",
        secret_key="test-secret-that-is-long-enough",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
    )

    with pytest.raises(EmailDeliveryError):
        send_password_reset_email(settings, "alex@example.com", "reset-token")

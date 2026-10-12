import smtplib
import ssl

import pytest
from api.app.config import Settings
from api.app.email import EmailDeliveryError, send_password_reset_email


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float, **kwargs: object) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.tls_context = kwargs.get('context')
        self.login_values: tuple[str, str] | None = None
        self.messages = []
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self, **kwargs: object) -> None:
        self.started_tls = True
        self.tls_context = kwargs.get('context')

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
        _env_file=None,
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
    assert (
        "source=email&token=reset-token"
        in message.get_body(preferencelist=("plain",)).get_content()
    )
    html = message.get_body(preferencelist=("html",)).get_content()
    assert message.get_content_type() == "multipart/alternative"
    assert message["From"] == "PromptVault <no-reply@example.com>"
    assert "Reset password</a>" in html
    assert (
        'href="https://app.example.com/reset-password?source=email&amp;token=reset-token"' in html
    )
    assert "30 minutes" in html
    assert "font-family:Inter,Arial,sans-serif" in html
    assert 'src="cid:promptvault-logo"' in html
    logo = next(part for part in message.walk() if part.get_content_type() == "image/png")
    assert logo["Content-ID"] == "<promptvault-logo>"
    assert logo.get_content_disposition() == "inline"
    assert logo.get_payload(decode=True).startswith(b"\x89PNG\r\n\x1a\n")


def test_password_reset_email_requires_smtp_configuration() -> None:
    settings = Settings(
        _env_file=None,
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
        _env_file=None,
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault",
        secret_key="test-secret-that-is-long-enough",
        smtp_host="smtp.example.com",
        smtp_from_email="no-reply@example.com",
    )

    with pytest.raises(EmailDeliveryError):
        send_password_reset_email(settings, "alex@example.com", "reset-token")


def test_password_reset_email_uses_implicit_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr("api.app.email.smtplib.SMTP_SSL", FakeSMTP)
    settings = Settings(
        _env_file=None,
        database_url="postgresql://localhost/promptvault",
        secret_key="test-secret",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_ssl=True,
        smtp_starttls=False,
        smtp_from_email="no-reply@example.com",
    )
    send_password_reset_email(settings, "alex@example.com", "reset-token")
    client = FakeSMTP.instances[0]
    assert client.port == 465
    assert not client.started_tls
    assert len(client.messages) == 1


def test_password_reset_email_hides_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_login(*_: object) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"sensitive server response")

    monkeypatch.setattr("api.app.email.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr(FakeSMTP, "login", reject_login)
    settings = Settings(
        _env_file=None,
        database_url="postgresql://localhost/promptvault",
        secret_key="test-secret",
        smtp_host="smtp.example.com",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_from_email="no-reply@example.com",
    )
    with pytest.raises(EmailDeliveryError, match="^SMTP delivery failed$"):
        send_password_reset_email(settings, "alex@example.com", "reset-token")


@pytest.mark.parametrize('implicit_tls', [False, True])
def test_smtp_verifies_certificates_when_python_system_trust_store_is_empty(
    monkeypatch: pytest.MonkeyPatch, implicit_tls: bool,
) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr('api.app.email.smtplib.SMTP', FakeSMTP)
    monkeypatch.setattr('api.app.email.smtplib.SMTP_SSL', FakeSMTP)
    monkeypatch.setattr('api.app.email.ssl.create_default_context',
                        lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    settings = Settings(
        _env_file=None, database_url='postgresql://localhost/promptvault', secret_key='test-secret',
        smtp_host='smtp.example.com', smtp_port=465 if implicit_tls else 587,
        smtp_ssl=implicit_tls, smtp_starttls=not implicit_tls, smtp_from_email='sender@example.com',
    )
    send_password_reset_email(settings, 'alex@example.com', 'reset-token')
    context = FakeSMTP.instances[0].tls_context
    assert context.cert_store_stats()['x509_ca'] > 0
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True

"""SMTP delivery for transactional application email."""

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from api.app.config import Settings


class EmailDeliveryError(RuntimeError):
    """Raised when a configured SMTP server cannot deliver a message."""


def _reset_url(settings: Settings, token: str) -> str:
    parts = urlsplit(settings.password_reset_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def send_password_reset_email(settings: Settings, recipient: str, token: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP is not configured")

    reset_url = _reset_url(settings, token)
    message = EmailMessage()
    message["Subject"] = "Reset your PromptVault password"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your PromptVault account.\n\n"
        f"Reset your password: {reset_url}\n\n"
        f"This link expires in {settings.password_reset_ttl_minutes} minutes and can be used once. "
        "If you did not request it, you can ignore this email."
    )

    try:
        if settings.smtp_ssl:
            client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        with client:
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP delivery failed") from exc

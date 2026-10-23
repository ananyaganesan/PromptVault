"""SMTP delivery for transactional application email."""

import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import certifi

from api.app.config import Settings

_RESET_TEMPLATE = Template(
    (Path(__file__).parent / "templates" / "password-reset.html").read_text(encoding="utf-8")
)
_PASSWORD_CHANGED_TEMPLATE = Template(
    (Path(__file__).parent / "templates" / "password-changed.html").read_text(encoding="utf-8")
)
_INVITATION_TEMPLATE = Template(
    (Path(__file__).parent / "templates" / "project-invitation.html").read_text(encoding="utf-8")
)
_VERIFICATION_TEMPLATE = Template(
    (Path(__file__).parent / "templates" / "email-verification.html").read_text(encoding="utf-8")
)
_LOGO_PNG = (Path(__file__).parent / "templates" / "assets" / "promptvault-logo.png").read_bytes()


class EmailDeliveryError(RuntimeError):
    """Raised when a configured SMTP server cannot deliver a message."""


def _smtp_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    # Some local Python installations have an empty system trust store. Add the
    # same maintained public CA bundle used by HTTPX without removing custom CAs.
    context.load_verify_locations(cafile=certifi.where())
    return context


def _reset_url(settings: Settings, token: str) -> str:
    parts = urlsplit(settings.password_reset_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _verification_url(settings: Settings, token: str) -> str:
    parts = urlsplit(settings.email_verification_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def send_password_changed_email(settings: Settings, recipient: str) -> None:
    """Notify an account holder after their password reset has completed."""
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "Your PromptVault password has been changed"
    message["From"] = f"PromptVault <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        "Your PromptVault password has been changed successfully.\n\n"
        "If you made this change, no further action is needed. "
        "If you did not make this change, reset your password immediately "
        "and contact an administrator."
    )
    message.add_alternative(_PASSWORD_CHANGED_TEMPLATE.substitute(), subtype="html")
    _attach_logo(message)
    _send_message(settings, message)


def send_project_invitation_email(
    settings: Settings, recipient: str, token: str, project_name: str, inviter_name: str
) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP is not configured")
    # Fragments do not enter HTTP request/access logs or Referer headers.
    invitation_url = f"{settings.project_invitation_url}#token={token}"
    message = EmailMessage()
    message["Subject"] = "Invitation to join a PromptVault project"
    message["From"] = f"PromptVault <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        f"{inviter_name} invited you to join {project_name} on PromptVault.\n\n"
        f"Review and accept: {invitation_url}\n\n"
        "Sign in to the account receiving this email, then choose Accept invitation. "
        "This link expires in seven days and can be used once. "
        "You will only get project access after accepting. "
        "If you do not want to join, ignore this email."
    )
    message.add_alternative(
        _INVITATION_TEMPLATE.substitute(
            invitation_url=escape(invitation_url, quote=True),
            project_name=escape(project_name),
            inviter_name=escape(inviter_name),
        ),
        subtype="html",
    )
    _attach_logo(message)
    _send_message(settings, message)


def _send_message(settings: Settings, message: EmailMessage) -> None:
    smtp_host = settings.smtp_host
    if not smtp_host:
        raise EmailDeliveryError("SMTP is not configured")
    try:
        client: smtplib.SMTP
        if settings.smtp_ssl:
            client = smtplib.SMTP_SSL(
                smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=_smtp_tls_context(),
            )
        else:
            client = smtplib.SMTP(
                smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        with client:
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls(context=_smtp_tls_context())
                client.ehlo()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP delivery failed") from exc


def _attach_logo(message: EmailMessage) -> None:
    html_part = message.get_body(preferencelist=("html",))
    if html_part is None:
        raise EmailDeliveryError("HTML email could not be constructed")
    html_part.add_related(
        _LOGO_PNG,
        maintype="image",
        subtype="png",
        cid="<promptvault-logo>",
        disposition="inline",
        filename="promptvault-logo.png",
    )


def send_password_reset_email(settings: Settings, recipient: str, token: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP is not configured")

    reset_url = _reset_url(settings, token)
    message = EmailMessage()
    message["Subject"] = "Reset your PromptVault password"
    message["From"] = f"PromptVault <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your PromptVault account.\n\n"
        f"Reset your password: {reset_url}\n\n"
        f"This link expires in {settings.password_reset_ttl_minutes} minutes and can be used once. "
        "If you did not request it, you can ignore this email."
    )
    message.add_alternative(
        _RESET_TEMPLATE.substitute(
            reset_url=escape(reset_url, quote=True),
            expiry_minutes=settings.password_reset_ttl_minutes,
        ),
        subtype="html",
    )
    _attach_logo(message)
    _send_message(settings, message)


def send_email_verification_email(settings: Settings, recipient: str, token: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP is not configured")

    verification_url = _verification_url(settings, token)
    message = EmailMessage()
    message["Subject"] = "Verify your PromptVault email"
    message["From"] = f"PromptVault <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        "Verify the email address for your PromptVault account.\n\n"
        f"Verify your email: {verification_url}\n\n"
        f"This link expires in {settings.email_verification_ttl_minutes} minutes and can be "
        "used once. If you did not create this account, you can ignore this email."
    )
    message.add_alternative(
        _VERIFICATION_TEMPLATE.substitute(
            verification_url=escape(verification_url, quote=True),
            expiry_minutes=settings.email_verification_ttl_minutes,
        ),
        subtype="html",
    )
    _attach_logo(message)
    _send_message(settings, message)

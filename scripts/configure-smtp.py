#!/usr/bin/env python3
"""Configure Gmail password-reset delivery without putting secrets in shell history."""

import argparse
import getpass
import os
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    from api.app.config import Settings

    env_path = REPOSITORY_ROOT / ".env"
    if not env_path.is_file():
        print("Copy .env.example to .env before configuring SMTP.", file=sys.stderr)
        return 1
    existing = dotenv_values(env_path)
    default_sender = existing.get("SMTP_FROM_EMAIL") or existing.get("SMTP_USERNAME") or ""
    sender_prompt = f"Gmail/Google Workspace sender address [{default_sender}]: " if default_sender else (
        "Gmail/Google Workspace sender address: "
    )
    sender = input(sender_prompt).strip() or default_sender
    default_url = existing.get("PASSWORD_RESET_URL") or "http://localhost:5173/reset-password"
    reset_url = input(f"Frontend reset-password URL [{default_url}]: ").strip() or default_url
    password = getpass.getpass("Google App Password (hidden): ").replace(" ", "")
    if not sender or not password:
        print("Sender and App Password are required; .env was not changed.", file=sys.stderr)
        return 1
    updates = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": sender,
        "SMTP_PASSWORD": password,
        "SMTP_FROM_EMAIL": sender,
        "SMTP_STARTTLS": "true",
        "SMTP_SSL": "false",
        "PASSWORD_RESET_URL": reset_url,
    }
    try:
        Settings(_env_file=None, **{
            key.lower(): value for key, value in (existing | updates).items()
            if value is not None
        })
    except ValidationError as exc:
        # ValidationError's default string can include input values, including secrets.
        for error in exc.errors(include_input=False):
            print(f"Invalid configuration: {error['msg']}", file=sys.stderr)
        return 1

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=env_path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(env_path.read_text())
        for key, value in updates.items():
            set_key(temporary_path, key, value)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, env_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print("SMTP settings saved to .env with owner-only permissions.")
    print("Rebuild/recreate the API: docker compose up -d --build --force-recreate api")
    print("Then request a password reset for an existing account to verify email delivery.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; SMTP setup was not completed.", file=sys.stderr)
        raise SystemExit(1) from None

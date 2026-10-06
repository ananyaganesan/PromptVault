#!/usr/bin/env python3
"""Validate production operator inputs without printing secret values."""

from __future__ import annotations

import argparse
import os
import socket
import ssl
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

BASE_SECRETS = {
    "postgres_owner_password",
    "migration_database_url",
    "runtime_database_password",
    "runtime_database_url",
    "secret_key",
    "provider_encryption_key",
    "redis_password",
    "rate_limit_redis_url",
}


def required_secret_names(
    *, require_smtp: bool = True, require_alerting: bool = True,
    require_offsite: bool = True,
) -> set[str]:
    names = set(BASE_SECRETS)
    if require_smtp:
        names.add("smtp_password")
    if require_alerting:
        names.add("alert_webhook_url")
    if require_offsite:
        names.update(("restic_password", "restic_credentials"))
    return names


def validate_secret_directory(directory: Path, names: set[str]) -> list[str]:
    if not directory.is_dir():
        return [f"SECRET_DIR does not exist or is not a directory: {directory}"]
    errors: list[str] = []
    for name in sorted(names):
        path = directory / name
        if not path.exists():
            errors.append(f"secret {name} is missing from SECRET_DIR")
            continue
        if path.is_symlink() or not path.is_file():
            errors.append(f"secret {name} must be a regular file, not a symlink")
            continue
        if stat.S_IMODE(path.stat().st_mode) not in {0o400, 0o600}:
            errors.append(f"secret {name} must use mode 0400 or 0600")
        if not path.read_bytes().strip():
            errors.append(f"secret {name} must not be empty")
    return errors


def validate_alert_webhook(path: Path) -> list[str]:
    if not path.is_file() or path.is_symlink():
        return []
    parsed = urlsplit(path.read_text().strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return ["alert_webhook_url must contain an absolute HTTPS URL"]
    return []


def _missing(environment: Mapping[str, str], name: str) -> bool:
    return not environment.get(name, "").strip()


def validate_environment(
    environment: Mapping[str, str], *, require_smtp: bool = True,
    require_offsite: bool = True,
) -> list[str]:
    errors: list[str] = []
    domain = environment.get("DOMAIN", "").strip().lower()
    if not domain:
        errors.append("DOMAIN is required")
    elif (
        domain in {"localhost", "promptvault.example.com"}
        or domain.endswith(".example.com")
        or "." not in domain
    ):
        errors.append("DOMAIN must be a real public hostname, not a placeholder")

    if require_smtp:
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_FROM_EMAIL"):
            if _missing(environment, name):
                errors.append(f"{name} is required when SMTP verification is enabled")
        try:
            port = int(environment.get("SMTP_PORT", "587"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            errors.append("SMTP_PORT must be an integer between 1 and 65535")

    if require_offsite and _missing(environment, "RESTIC_REPOSITORY"):
        errors.append("RESTIC_REPOSITORY is required for encrypted off-site backups")
    return errors


def validate_dns(domain: str) -> list[str]:
    try:
        addresses = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return [f"DOMAIN does not resolve: {exc}"]
    if not addresses:
        return ["DOMAIN does not resolve to any address"]
    return []


def validate_tls(domain: str) -> list[str]:
    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((domain, 443), timeout=10) as connection,
            context.wrap_socket(connection, server_hostname=domain),
        ):
            pass
    except (OSError, ssl.SSLError) as exc:
        return [f"HTTPS certificate/reachability check failed: {exc}"]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--secret-dir",
        type=Path,
        default=Path(os.getenv("SECRET_DIR", "./secrets")),
    )
    parser.add_argument("--offline", action="store_true", help="Skip DNS and TLS probes")
    parser.add_argument("--skip-smtp", action="store_true")
    parser.add_argument("--skip-alerting", action="store_true")
    parser.add_argument("--skip-offsite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    require_smtp = not args.skip_smtp
    require_alerting = not args.skip_alerting
    require_offsite = not args.skip_offsite
    errors = validate_environment(
        os.environ,
        require_smtp=require_smtp,
        require_offsite=require_offsite,
    )
    errors.extend(
        validate_secret_directory(
            args.secret_dir,
            required_secret_names(
                require_smtp=require_smtp,
                require_alerting=require_alerting,
                require_offsite=require_offsite,
            ),
        )
    )
    if require_alerting:
        errors.extend(validate_alert_webhook(args.secret_dir / "alert_webhook_url"))
    domain = os.getenv("DOMAIN", "").strip()
    if not args.offline and domain and not any(error.startswith("DOMAIN") for error in errors):
        errors.extend(validate_dns(domain))
        if not errors:
            errors.extend(validate_tls(domain))
    if errors:
        print("Production preflight failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    mode = "offline configuration" if args.offline else "live DNS/TLS"
    print(f"Production preflight passed ({mode}); secret values were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

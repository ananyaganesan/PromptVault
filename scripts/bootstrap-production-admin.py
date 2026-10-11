#!/usr/bin/env python3
"""Create the first production Super Admin without loading demo seeds."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

import psycopg

from api.app.schemas.auth import RegisterRequest
from api.app.security import hash_password


def read_private_password(path: Path | None) -> str:
    if path is not None:
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or stat.S_IMODE(mode) & 0o077:
            raise ValueError("admin password file must be regular and owner-only")
        password = path.read_text(encoding="utf-8").strip()
    else:
        password = os.environ.pop("PRODUCTION_ADMIN_PASSWORD", "").strip()
    if not password:
        raise ValueError("admin password is required")
    return password


def bootstrap(database_url: str, *, email: str, display_name: str, password: str) -> None:
    payload = RegisterRequest.model_validate(
        {"email": email, "display_name": display_name, "password": password}
    )
    password_hash = hash_password(payload.password.get_secret_value())
    with psycopg.connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('promptvault_admin_bootstrap'))")
        if connection.execute(
            "SELECT 1 FROM users WHERE role = 'admin' AND is_active LIMIT 1"
        ).fetchone():
            raise RuntimeError("an active Super Admin already exists")
        if connection.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(%s)", (str(payload.email),)
        ).fetchone():
            raise RuntimeError("the bootstrap email already belongs to an account")
        connection.execute(
            """
            INSERT INTO users (email, display_name, password_hash, role, is_active)
            VALUES (%s, %s, %s, 'admin', TRUE)
            """,
            (str(payload.email), payload.display_name, password_hash),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("MIGRATION_DATABASE_URL"))
    parser.add_argument("--email", default=os.getenv("PRODUCTION_ADMIN_EMAIL"))
    parser.add_argument("--display-name", default=os.getenv("PRODUCTION_ADMIN_DISPLAY_NAME"))
    parser.add_argument("--password-file", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if not args.database_url:
            raise ValueError("MIGRATION_DATABASE_URL is required")
        if not args.email or not args.display_name:
            raise ValueError("production admin email and display name are required")
        bootstrap(
            args.database_url,
            email=args.email,
            display_name=args.display_name,
            password=read_private_password(args.password_file),
        )
    except psycopg.Error:
        print("Admin bootstrap failed: database operation failed", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Admin bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print("Initial production Super Admin created; rotate the bootstrap password after login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create or rotate the restricted PostgreSQL login used by the production API."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

import psycopg
from psycopg import sql

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def role_identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("role name must be a safe PostgreSQL identifier")
    return value


def role_password_statement(
    action: str, role: str, password: str
) -> sql.Composed:
    if action not in {"CREATE", "ALTER"}:
        raise ValueError("role password action must be CREATE or ALTER")
    return sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
        sql.SQL(action),
        sql.Identifier(role),
        sql.Literal(password),
    )


def read_private_secret(path: Path) -> str:
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("password file must be a regular file")
    if stat.S_IMODE(mode) & 0o077:
        raise ValueError("password file must use owner-only permissions")
    secret = path.read_text(encoding="utf-8").strip()
    if not secret:
        raise ValueError("password file must not be empty")
    return secret


def resolve_password(password_file: Path | None) -> str:
    if password_file is not None:
        return read_private_secret(password_file)
    secret = os.environ.pop("RUNTIME_DATABASE_PASSWORD", "").strip()
    if not secret:
        raise ValueError(
            "--password-file or RUNTIME_DATABASE_PASSWORD is required"
        )
    return secret


def provision(database_url: str, role: str, password: str) -> None:
    identifier = sql.Identifier(role)
    with psycopg.connect(database_url, autocommit=True) as connection:
        group_exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = 'promptvault_app'"
        ).fetchone()
        if group_exists is None:
            raise RuntimeError("promptvault_app role is missing; run migrations first")
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
        ).fetchone()
        if exists is None:
            connection.execute(role_password_statement("CREATE", role, password))
        else:
            connection.execute(role_password_statement("ALTER", role, password))
        connection.execute(sql.SQL("GRANT promptvault_app TO {}").format(identifier))
        connection.execute(
            sql.SQL("ALTER ROLE {} SET statement_timeout TO '30s'").format(identifier)
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout TO '30s'").format(
                identifier
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("MIGRATION_DATABASE_URL"),
        help="Owner connection used only for provisioning",
    )
    parser.add_argument("--role", default="promptvault_runtime")
    parser.add_argument(
        "--password-file",
        type=Path,
        help="Owner-only password file (preferred outside the Compose bootstrap)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if not args.database_url:
            raise ValueError("MIGRATION_DATABASE_URL is required")
        role = role_identifier(args.role)
        password = resolve_password(args.password_file)
        provision(args.database_url, role, password)
    except psycopg.Error:
        print("Runtime-role provisioning failed: database operation failed", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Runtime-role provisioning failed: {exc}", file=sys.stderr)
        return 1
    print(f"Restricted production login ready: {role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

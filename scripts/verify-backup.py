#!/usr/bin/env python3
"""Prove that the running Compose database can be dumped and restored safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import BinaryIO
from uuid import uuid4

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_COUNT_TABLES = (
    "schema_migrations",
    "users",
    "projects",
    "prompts",
    "prompt_versions",
    "runs",
    "deployments",
    "api_tokens",
    "audit_events",
)
_COUNTS_SQL = "SELECT json_build_object(" + ", ".join(
    f"'{table}', (SELECT count(*) FROM {table})" for table in _COUNT_TABLES
) + ")::text"


class BackupVerificationError(RuntimeError):
    """Raised when a disposable dump/restore drill cannot be completed."""


def database_identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("database name must be a safe PostgreSQL identifier")
    return value


def parse_counts(value: str) -> dict[str, int]:
    try:
        payload = json.loads(value)
        if (
            not isinstance(payload, dict)
            or set(payload) != set(_COUNT_TABLES)
            or any(
                not isinstance(payload[table], int) or payload[table] < 0
                for table in _COUNT_TABLES
            )
        ):
            raise ValueError
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid database count payload") from exc
    return {table: payload[table] for table in _COUNT_TABLES}


def _compose_command(service: str, *arguments: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", service, *arguments]


def _run(
    arguments: list[str],
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | int | None = subprocess.PIPE,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        arguments,
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise BackupVerificationError(message or "database utility failed")
    return result


def _database_counts(*, service: str, user: str, database: str) -> dict[str, int]:
    result = _run(
        _compose_command(
            service,
            "psql",
            "-X",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--quiet",
            "--username",
            user,
            "--dbname",
            database,
            "--command",
            _COUNTS_SQL,
        )
    )
    return parse_counts(result.stdout.decode().strip())


def verify_backup(*, service: str, user: str, database: str) -> dict[str, int]:
    service = database_identifier(service)
    user = database_identifier(user)
    database = database_identifier(database)
    scratch_database = database_identifier(
        f"promptvault_restore_verify_{uuid4().hex[:12]}"
    )
    source_counts = _database_counts(service=service, user=user, database=database)
    scratch_created = False

    with tempfile.TemporaryFile() as backup:
        try:
            _run(
                _compose_command(
                    service,
                    "pg_dump",
                    "--username",
                    user,
                    "--dbname",
                    database,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                ),
                stdout=backup,
            )
            backup_size = backup.tell()
            if backup_size <= 0:
                raise BackupVerificationError("database dump was empty")

            _run(
                _compose_command(
                    service,
                    "createdb",
                    "--username",
                    user,
                    "--template",
                    "template0",
                    scratch_database,
                )
            )
            scratch_created = True
            backup.seek(0)
            _run(
                _compose_command(
                    service,
                    "pg_restore",
                    "--username",
                    user,
                    "--dbname",
                    scratch_database,
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                ),
                stdin=backup,
            )
            restored_counts = _database_counts(
                service=service,
                user=user,
                database=scratch_database,
            )
            if restored_counts != source_counts:
                raise BackupVerificationError(
                    "restored critical table counts do not match the source database"
                )
            return source_counts
        finally:
            if scratch_created:
                _run(
                    _compose_command(
                        service,
                        "dropdb",
                        "--username",
                        user,
                        "--if-exists",
                        "--force",
                        scratch_database,
                    )
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default="db", help="Compose PostgreSQL service name")
    parser.add_argument("--user", default=os.getenv("POSTGRES_USER", "promptvault"))
    parser.add_argument("--database", default=os.getenv("POSTGRES_DB", "promptvault"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        counts = verify_backup(
            service=args.service,
            user=args.user,
            database=args.database,
        )
    except (BackupVerificationError, OSError, ValueError) as exc:
        print(f"Backup restore verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Backup restore verified in an isolated database: "
        f"{counts['schema_migrations']} migrations, {counts['runs']} runs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

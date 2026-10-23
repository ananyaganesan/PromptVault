"""Create a native PostgreSQL backup and verify it in an isolated restore database."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from api.app.config import Settings


def tool_environment(url: str, *, database: str | None = None) -> dict[str, str]:
    parameters = conninfo_to_dict(url)
    environment = {**os.environ}
    for key, variable in [
        ("host", "PGHOST"),
        ("port", "PGPORT"),
        ("user", "PGUSER"),
        ("password", "PGPASSWORD"),
        ("dbname", "PGDATABASE"),
    ]:
        if key in parameters:
            environment[variable] = parameters[key]
    if database:
        environment["PGDATABASE"] = database
    return environment


def counts(connection: psycopg.Connection) -> dict[str, int]:
    names = connection.execute("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relispartition
        ORDER BY c.relname
    """).fetchall()
    return {
        name: connection.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("public", name))
        ).fetchone()[0]
        for (name,) in names
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--admin-url", help="Restore administrator DSN; prefer .pgpass for its password"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "evidence/database/backup-restore.json"
    )
    args = parser.parse_args()
    source = Settings(_env_file=ROOT / ".env").database_url
    backup = args.output or ROOT / "secrets/backups" / (
        "promptvault-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".dump"
    )
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never overwrite an earlier backup, and keep its contents private from creation.
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    dump_completed = False
    try:
        with (
            os.fdopen(descriptor, "wb") as output,
            psycopg.connect(source) as connection,
        ):
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            expected = counts(connection)
            revision = connection.execute(
                "SELECT max(version) FROM schema_migrations"
            ).fetchone()[0]
            subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot",
                    snapshot,
                ],
                env=tool_environment(source),
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
            )
        dump_completed = True
        report = {
            "checked_at": datetime.now(UTC).isoformat(),
            "migration_version": revision,
            "logical_table_count": len(expected),
            "source_counts": expected,
            "native_tools": ["pg_dump", "pg_restore"],
            "restore_verified": False,
        }
        admin_url = args.admin_url or source
        target = "promptvault_restore_" + uuid4().hex[:12] + "_test"
        created = False
        with psycopg.connect(admin_url, autocommit=True) as admin:
            # Resolve pgpass once: its entry may be scoped to the maintenance database.
            restore_environment = tool_environment(admin_url, database=target)
            if admin.info.password:
                restore_environment["PGPASSWORD"] = admin.info.password
            try:
                admin.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target))
                )
                created = True
                subprocess.run(
                    [
                        "pg_restore",
                        "--no-owner",
                        "--no-acl",
                        "--exit-on-error",
                        "--dbname",
                        target,
                        str(backup),
                    ],
                    env=restore_environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                from psycopg.conninfo import make_conninfo

                with psycopg.connect(
                    make_conninfo(
                        admin_url, dbname=target, password=admin.info.password
                    )
                ) as restored:
                    actual = counts(restored)
                    if actual != expected:
                        raise RuntimeError(
                            "Restored table counts differ from the backup snapshot"
                        )
                    report.update(restore_verified=True, restored_counts=actual)
            finally:
                if created:
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                            sql.Identifier(target)
                        )
                    )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"Native backup and isolated restore verified: {len(expected)} tables, migration {revision}."
        )
        print(
            "Backup retained privately; verification database removed. Report:",
            args.report,
        )
        return 0
    except (
        OSError,
        psycopg.Error,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        if not dump_completed:
            backup.unlink(missing_ok=True)
        # PostgreSQL errors can embed DSNs/values. Report the category only.
        print(
            "Backup/restore verification failed:", type(error).__name__, file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

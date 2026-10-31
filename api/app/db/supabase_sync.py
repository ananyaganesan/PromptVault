"""One-way snapshot reconciliation for the small local demonstration database.

The source is always read-only. Only changed rows cross the connection. The
destination remains an atomic copy of a committed source snapshot, including
deletions, without replaying application audit or authentication triggers.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from api.app.db.migrations import AppliedMigration, discover_migrations, plan_migrations
from psycopg import sql


class SyncRefused(RuntimeError):
    """A safe, credential-free explanation for a refused reconciliation."""


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[tuple[Any, ...], ...]
    primary_key: tuple[str, ...]

    @property
    def identifier(self) -> sql.Identifier:
        return sql.Identifier("public", self.name)

    @property
    def key_expression(self) -> sql.Composed:
        return sql.SQL("pg_catalog.jsonb_build_array({})").format(
            sql.SQL(",").join(sql.Identifier("t", name) for name in self.primary_key)
        )


def prepare_session(connection: psycopg.Connection, *, source: bool) -> None:
    if source:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    connection.execute("SET LOCAL DateStyle='ISO,YMD'")
    connection.execute("SET LOCAL search_path=pg_catalog,public")
    connection.execute("SET LOCAL statement_timeout='30s'")
    connection.execute("SET LOCAL lock_timeout='3s'")


def read_tables(connection: psycopg.Connection) -> list[Table]:
    result = connection.execute("""
        SELECT c.relname,
          (SELECT jsonb_agg(jsonb_build_array(a.attname,format_type(a.atttypid,a.atttypmod),
                    a.attnotnull,a.attidentity,a.attgenerated) ORDER BY a.attnum)
           FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
          (SELECT array_agg(a.attname ORDER BY k.ordinality)
           FROM pg_index i CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ordinality)
           JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
           WHERE i.indrelid=c.oid AND i.indisprimary)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relispartition
        ORDER BY c.relname
    """).fetchall()
    tables = [
        Table(name, tuple(tuple(c) for c in columns), tuple(pk or ()))
        for name, columns, pk in result
    ]
    if not tables or any(not table.primary_key for table in tables):
        raise SyncRefused("Every mirrored table must have a primary key")
    return tables


def migration_history(connection: psycopg.Connection) -> list[tuple]:
    return connection.execute(
        "SELECT version,name,checksum FROM public.schema_migrations ORDER BY version"
    ).fetchall()


def manifest(connection: psycopg.Connection, tables: list[Table]) -> dict[str, dict]:
    statements = [
        sql.SQL("""
        SELECT {}::text AS table_name, count(*) AS rows,
          md5(coalesce(string_agg(to_jsonb(t)::text,E'\\n'
              ORDER BY to_jsonb(t)::text COLLATE "C"),'')) AS digest
        FROM {} AS t
    """).format(sql.Literal(table.name), table.identifier)
        for table in tables
    ]
    return {
        name: {"rows": count, "digest": digest}
        for name, count, digest in connection.execute(
            sql.SQL(" UNION ALL ").join(statements)
        ).fetchall()
    }


def row_fingerprints(connection: psycopg.Connection, table: Table) -> dict[str, str]:
    return dict(
        connection.execute(
            sql.SQL("SELECT {}::text, md5(to_jsonb(t)::text) FROM {} AS t").format(
                table.key_expression, table.identifier
            )
        ).fetchall()
    )


def source_rows(connection: psycopg.Connection, table: Table) -> dict[str, tuple[str, str]]:
    return {
        key: (digest, value)
        for key, digest, value in connection.execute(
            sql.SQL("SELECT {}::text,md5(to_jsonb(t)::text),to_jsonb(t)::text FROM {} AS t").format(
                table.key_expression, table.identifier
            )
        ).fetchall()
    }


def load_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(state, output, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def initial_baseline(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        item["table_name"]: {"rows": item["rows"], "digest": item["digest"]}
        for item in json.loads(path.read_text()).get("manifest", [])
    }


def ensure_partitions(source: psycopg.Connection, target: psycopg.Connection) -> int:
    query = """
      SELECT c.relname,p.relname,pg_get_expr(c.relpartbound,c.oid)
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_inherits i ON i.inhrelid=c.oid JOIN pg_class p ON p.oid=i.inhparent
      JOIN pg_namespace pn ON pn.oid=p.relnamespace
      WHERE n.nspname='public' AND pn.nspname='public' AND c.relispartition
        AND c.relkind IN ('r','p')
      ORDER BY c.relname
    """
    expected = {name: (parent, bound) for name, parent, bound in source.execute(query)}
    actual = {name: (parent, bound) for name, parent, bound in target.execute(query)}
    created = 0
    for name, (parent, bound) in expected.items():
        if name in actual:
            if actual[name] != (parent, bound):
                raise SyncRefused("Partition definitions differ; apply matching schema changes")
            continue
        # The bound is PostgreSQL-generated catalog SQL, never supplied by a row.
        target.execute(
            sql.SQL("CREATE TABLE {} PARTITION OF {} {}").format(
                sql.Identifier("public", name), sql.Identifier("public", parent), sql.SQL(bound)
            )
        )
        target.execute(
            sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(
                sql.Identifier("public", name)
            )
        )
        for role, policy in (
            ("promptvault_app", "promptvault_backend_access"),
            ("promptvault_readonly", "promptvault_readonly_access"),
        ):
            if target.execute(
                "SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=%s)", (role,)
            ).fetchone()[0]:
                target.execute(
                    sql.SQL("CREATE POLICY {} ON {} TO {} USING(true) WITH CHECK(true)").format(
                        sql.Identifier(policy), sql.Identifier("public", name), sql.Identifier(role)
                    )
                )
        created += 1
    return created


def sync_sequences(source: psycopg.Connection, target: psycopg.Connection) -> None:
    sequences = source.execute("""
      SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind='S' ORDER BY c.relname
    """).fetchall()
    # Sequences are intentionally not rewound. PostgreSQL sequence changes are
    # nontransactional, and failed transactions are allowed to leave gaps.
    with target.pipeline():
        for (name,) in sequences:
            value, called = source.execute(
                sql.SQL("SELECT last_value,is_called FROM {}").format(
                    sql.Identifier("public", name)
                )
            ).fetchone()
            target.execute(
                sql.SQL("""
              SELECT setval(%s::regclass,GREATEST(last_value,%s),
                CASE WHEN last_value>%s THEN is_called ELSE is_called OR %s END)
              FROM {}
            """).format(sql.Identifier("public", name)),
                (sql.Identifier("public", name).as_string(), value, value, called),
            )


def reconcile(
    source: psycopg.Connection,
    target: psycopg.Connection,
    *,
    state_path: Path,
    baseline_path: Path,
    migrations_directory: Path | None = None,
) -> dict:
    """Commit one exact source snapshot to the destination, or roll back fully."""
    state = load_state(state_path)
    with source.transaction(), target.transaction():
        prepare_session(source, source=True)
        prepare_session(target, source=False)
        if (
            source.execute(
                "SELECT current_database(),inet_server_addr(),inet_server_port()"
            ).fetchone()
            == target.execute(
                "SELECT current_database(),inet_server_addr(),inet_server_port()"
            ).fetchone()
        ):
            raise SyncRefused("Source and destination must be different databases")
        if not target.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext('promptvault_local_to_supabase_sync'))"
        ).fetchone()[0]:
            raise SyncRefused("Another synchronization is already running")
        tables = read_tables(source)
        if tables != read_tables(target):
            raise SyncRefused("Table schemas differ; apply matching migrations before syncing")
        target.execute(
            sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                sql.SQL(",").join(table.identifier for table in tables)
            )
        )
        history = migration_history(source)
        if history != migration_history(target):
            raise SyncRefused("Migration history differs; apply matching migrations before syncing")
        if migrations_directory is not None and plan_migrations(
            discover_migrations(migrations_directory),
            {
                version: AppliedMigration(version, name, checksum)
                for version, name, checksum in history
            },
        ):
            raise SyncRefused("The local database has pending migrations")
        wanted = manifest(source, tables)
        current = manifest(target, tables)
        baseline = state.get("manifest") or initial_baseline(baseline_path)
        pending = state.get("pending_manifest", {})
        drift = [
            name
            for name in current
            if current[name] not in (wanted[name], baseline.get(name), pending.get(name))
        ]
        if drift:
            raise SyncRefused("Independent destination edits detected in: " + ", ".join(drift))
        changed = [table for table in tables if current[table.name] != wanted[table.name]]
        if any(table.name == "schema_migrations" for table in changed):
            raise SyncRefused("Migration records differ, including their application timestamps")
        plans = []
        counts = {"inserted": 0, "updated": 0, "deleted": 0}
        for table in changed:
            local = source_rows(source, table)
            remote = row_fingerprints(target, table)
            removed = [key for key in remote if key not in local or remote[key] != local[key][0]]
            added = [
                value
                for key, (digest, value) in local.items()
                if key not in remote or digest != remote[key]
            ]
            counts["deleted"] += sum(key not in local for key in remote)
            counts["updated"] += sum(
                key in local and remote[key] != local[key][0] for key in remote
            )
            counts["inserted"] += sum(key not in remote for key in local)
            plans.append((table, removed, added))
        state["pending_manifest"] = wanted
        save_state(state_path, state)  # Durable before commit, for interrupted workers.
        partitions_created = ensure_partitions(source, target)
        if changed:
            target.execute("SET LOCAL session_replication_role=replica")
            with target.pipeline():
                for table, removed, _ in plans:
                    if removed:
                        target.execute(
                            sql.SQL("""
                          DELETE FROM {} AS t WHERE {} IN (
                            SELECT value FROM jsonb_array_elements(%s::jsonb))
                        """).format(table.identifier, table.key_expression),
                            ("[" + ",".join(removed) + "]",),
                        )
                for table, _, added in plans:
                    if added:
                        names = sql.SQL(",").join(
                            sql.Identifier(column[0]) for column in table.columns if not column[4]
                        )
                        target.execute(
                            sql.SQL("""
                          INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE
                          SELECT {} FROM jsonb_populate_recordset(NULL::{},%s::jsonb)
                        """).format(table.identifier, names, names, table.identifier),
                            ("[" + ",".join(added) + "]",),
                        )
            target.execute("SET LOCAL session_replication_role=origin")
            if manifest(target, tables) != wanted:
                raise SyncRefused("Content verification failed; destination changes rolled back")
            for (name,) in target.execute(
                "SELECT matviewname FROM pg_matviews WHERE schemaname='public' ORDER BY matviewname"
            ).fetchall():
                target.execute(
                    sql.SQL("REFRESH MATERIALIZED VIEW {}").format(sql.Identifier("public", name))
                )
        sync_sequences(source, target)
    # Both connections have exited their transactions; target changes committed.
    state.update(
        manifest=wanted,
        pending_manifest={},
        last_success_at=datetime.now(UTC).isoformat(),
        last_error=None,
        changed_tables=[table.name for table in changed],
        partitions_created=partitions_created,
        **counts,
    )
    save_state(state_path, state)
    return {
        "tables_verified": len(tables),
        "changed_tables": len(changed),
        "partitions_created": partitions_created,
        **counts,
    }

"""Exercise mirror reconciliation against two disposable PostgreSQL databases."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from api.app.db import supabase_sync as sync

SCHEMA = """
CREATE TABLE schema_migrations(version bigint PRIMARY KEY,name text,checksum text,
  applied_at timestamptz NOT NULL);
INSERT INTO schema_migrations VALUES(1,'test',repeat('a',64),'2026-10-31T00:00:00Z');
CREATE TABLE parents(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  label text UNIQUE NOT NULL,amount numeric(30,12),payload jsonb,raw bytea);
CREATE TABLE children(id integer PRIMARY KEY,parent_id bigint REFERENCES parents(id)
  ON DELETE CASCADE,value text);
CREATE TABLE audit_events(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  operation text,parent_id bigint);
CREATE FUNCTION audit_parent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN INSERT INTO audit_events(operation,parent_id) VALUES(TG_OP,coalesce(NEW.id,OLD.id));
RETURN coalesce(NEW,OLD); END $$;
CREATE TRIGGER parent_audit AFTER INSERT OR UPDATE OR DELETE ON parents
  FOR EACH ROW EXECUTE FUNCTION audit_parent();
CREATE TABLE measurements(id integer,day date,value text,PRIMARY KEY(id,day))
  PARTITION BY RANGE(day);
CREATE TABLE measurements_2026 PARTITION OF measurements
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
INSERT INTO parents(label,amount,payload,raw)
  VALUES('original',1.123456789123,'{"nested":[true,null,"text"]}','\\x00ff');
INSERT INTO children VALUES(1,1,'unchanged child');
"""


@pytest.fixture
def databases(tmp_path: Path):
    admin_url = os.getenv(
        "SYNC_TEST_ADMIN_URL", "postgresql://postgres@localhost:5432/postgres"
    )
    try:
        admin = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip(
            "A local PostgreSQL administrator is required for isolated sync tests"
        )
    names = ["promptvault_sync_" + uuid4().hex[:12] + "_test" for _ in range(2)]
    connections = []
    try:
        for name in names:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            connection = psycopg.connect(
                make_conninfo(admin_url, dbname=name, password=admin.info.password),
                autocommit=True,
            )
            connection.execute(SCHEMA)
            connections.append(connection)
        yield (
            connections[0],
            connections[1],
            tmp_path / "state.json",
            tmp_path / "baseline.json",
        )
    finally:
        for connection in connections:
            connection.close()
        for name in names:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )
        admin.close()


def run(pair):
    source, target, state, baseline = pair
    return sync.reconcile(source, target, state_path=state, baseline_path=baseline)


def assert_same(pair):
    source, target, *_ = pair
    with source.transaction(), target.transaction():
        sync.prepare_session(source, source=True)
        sync.prepare_session(target, source=False)
        assert sync.manifest(source, sync.read_tables(source)) == sync.manifest(
            target, sync.read_tables(target)
        )


def test_insert_update_delete_precision_audit_and_retry(databases):
    source, target, *_ = databases
    assert run(databases)["changed_tables"] == 0
    source.execute("""
      UPDATE parents SET label='changed',amount=999999999999.123456789123,
        payload='{"unicode":"λ","n":999999999999999999.123456789123}' WHERE id=1;
      INSERT INTO parents(label,amount,raw) VALUES('second',2.0,'\\x0102');
      INSERT INTO children VALUES(2,2,'new child');
    """)
    result = run(databases)
    assert result["updated"] == 1
    assert result["inserted"] == 4  # parent, child, and two source audit rows
    assert target.execute("SELECT count(*) FROM children WHERE id=1").fetchone()[0] == 1
    assert_same(databases)
    assert run(databases)["changed_tables"] == 0
    source.execute("DELETE FROM parents WHERE id=2")
    assert run(databases)["deleted"] == 2
    assert_same(databases)
    assert (
        target.execute("SELECT current_setting('session_replication_role')").fetchone()[
            0
        ]
        == "origin"
    )
    assert (
        target.execute("SELECT last_value FROM audit_events_id_seq").fetchone()
        == source.execute("SELECT last_value FROM audit_events_id_seq").fetchone()
    )


def test_independent_destination_edits_are_never_overwritten(databases):
    source, target, *_ = databases
    run(databases)
    target.execute("UPDATE children SET value='remote edit' WHERE id=1")
    source.execute("UPDATE children SET value='local edit' WHERE id=1")
    with pytest.raises(sync.SyncRefused, match="Independent destination edits"):
        run(databases)
    assert target.execute("SELECT value FROM children").fetchone()[0] == "remote edit"


def test_invalid_delta_rolls_back_all_rows_and_session_settings(databases):
    source, target, *_ = databases
    run(databases)
    target.execute("ALTER TABLE parents ADD CONSTRAINT nonnegative CHECK(amount>=0)")
    before = target.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
    source.execute("UPDATE parents SET amount=-1 WHERE id=1")
    with pytest.raises(psycopg.errors.CheckViolation):
        run(databases)
    assert target.execute("SELECT amount>0 FROM parents").fetchone()[0]
    assert target.execute("SELECT * FROM audit_events ORDER BY id").fetchall() == before
    assert (
        target.execute("SELECT current_setting('session_replication_role')").fetchone()[
            0
        ]
        == "origin"
    )


def test_uncommitted_source_work_is_not_copied(databases):
    source, target, state, baseline = databases
    run(databases)
    with source.transaction():
        source.execute("UPDATE children SET value='committed later' WHERE id=1")
        with psycopg.connect(
            source.info.dsn, password=source.info.password, autocommit=True
        ) as reader:
            result = sync.reconcile(
                reader, target, state_path=state, baseline_path=baseline
            )
        assert result["changed_tables"] == 0
        assert (
            target.execute("SELECT value FROM children").fetchone()[0]
            == "unchanged child"
        )
    run(databases)
    assert_same(databases)


def test_schema_and_migration_drift_pause_synchronization(databases):
    source, target, *_ = databases
    run(databases)
    source.execute("ALTER TABLE children ADD COLUMN unexpected text")
    with pytest.raises(sync.SyncRefused, match="Table schemas differ"):
        run(databases)
    source.execute("ALTER TABLE children DROP COLUMN unexpected")
    target.execute("UPDATE schema_migrations SET checksum=repeat('b',64)")
    with pytest.raises(sync.SyncRefused, match="Migration history differs"):
        run(databases)


def test_commit_before_checkpoint_crash_recovers_without_losing_new_work(
    databases, monkeypatch
):
    source, target, *_ = databases
    run(databases)
    source.execute("UPDATE children SET value='first local edit' WHERE id=1")
    original = sync.save_state
    calls = 0

    def fail_after_commit(path, state):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated checkpoint interruption")
        original(path, state)

    with monkeypatch.context() as patch:
        patch.setattr(sync, "save_state", fail_after_commit)
        with pytest.raises(OSError):
            run(databases)
    assert (
        target.execute("SELECT value FROM children").fetchone()[0] == "first local edit"
    )
    source.execute("UPDATE children SET value='second local edit' WHERE id=1")
    run(databases)
    assert_same(databases)


def test_new_run_style_partition_is_created_and_secured(databases):
    source, target, *_ = databases
    run(databases)
    source.execute("""
      CREATE TABLE measurements_2027 PARTITION OF measurements
        FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
      INSERT INTO measurements VALUES(1,'2027-01-02','new partition row');
    """)
    assert run(databases)["partitions_created"] == 1
    assert target.execute(
        "SELECT relrowsecurity FROM pg_class WHERE oid='public.measurements_2027'::regclass"
    ).fetchone()[0]
    assert_same(databases)
    assert run(databases)["partitions_created"] == 0

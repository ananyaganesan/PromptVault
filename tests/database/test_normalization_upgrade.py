"""Data-preserving normalization and guarded deletion across an existing v029 graph."""

import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from api.app.db.migrations import (
    apply_migrations,
    discover_migrations,
    migrate_database,
)
from tests.database.test_migration_upgrade import temporary_database_url

__all__ = ["temporary_database_url"]
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_normalization_preserves_existing_graph_and_keeps_guarded_deletion_atomic(
    temporary_database_url: str,
) -> None:
    migrations = discover_migrations(ROOT / "db/migrations")
    uid, project, prompt = uuid4(), uuid4(), uuid4()
    config = json.dumps(
        {
            "provider": "mock",
            "model": "deterministic-v1",
            "temperature": 0,
            "max_output_tokens": 100,
        }
    )
    with psycopg.connect(temporary_database_url, autocommit=True) as c:
        apply_migrations(c, [m for m in migrations if m.version < 30])
        c.execute(
            "INSERT INTO users(id,email,display_name,password_hash,role,email_verified_at) VALUES(%s,%s,'Upgrade Admin','unused','admin',now())",
            (uid, "upgrade-" + uid.hex + "@example.com"),
        )
        c.execute(
            "INSERT INTO projects(id,name,key,owner_id) VALUES(%s,'Upgrade',%s,%s)",
            (project, "upgrade-" + project.hex, uid),
        )
        c.execute(
            "INSERT INTO prompts(id,project_id,key,name) VALUES(%s,%s,'reply','Reply')",
            (prompt, project),
        )
        versions = []
        for body in ["Hello {{name}}", "Welcome {{name}}"]:
            v = c.execute(
                "SELECT (create_prompt_version(%s,%s,%s,'[\"name\"]',%s::jsonb,'Upgrade',%s)).id",
                (prompt, versions[-1] if versions else None, body, config, uid),
            ).fetchone()[0]
            versions.append(v)
        run_id, run_time = c.execute(
            """SELECT r.id,r.created_at FROM record_run(
          %s,%s,%s,%s,'completed','mock','deterministic-v1','{"name":"Demo"}',
          'Mock fixture',2,2,25,0,NULL,'upgrade-check') r""",
            (uid, project, prompt, versions[1]),
        ).fetchone()
        reservation = c.execute(
            "SELECT (reserve_run_execution(%s,%s,%s,%s,'upgrade-idempotency-key',%s,%s,0,4)).id",
            (uid, project, prompt, versions[1], "a" * 64, uuid4()),
        ).fetchone()[0]
        c.execute(
            "SELECT finalize_run_execution(%s,'completed',0,%s,%s,NULL)",
            (reservation, run_id, run_time),
        )
        deployed = c.execute(
            "SELECT (request_deployment(%s,'prod',%s,'Upgrade')).id", (versions[1], uid)
        ).fetchone()[0]
        c.execute(
            "SELECT review_production_deployment(%s,%s,TRUE,'Checked')", (deployed, uid)
        )
        rollback = c.execute(
            "SELECT (rollback_deployment(%s,%s,%s,'Restore v1','prod')).id",
            (prompt, versions[0], uid),
        ).fetchone()[0]
    assert [
        m.version
        for m in migrate_database(temporary_database_url, ROOT / "db/migrations")
    ] == [30, 31]
    with psycopg.connect(temporary_database_url) as c:
        assert c.execute(
            "SELECT parent_version_id,variables FROM version_context WHERE id=%s",
            (versions[1],),
        ).fetchone() == (versions[0], ["name"])
        assert c.execute(
            "SELECT project_id,prompt_id,provider,model FROM run_context WHERE id=%s",
            (run_id,),
        ).fetchone() == (project, prompt, "mock", "deterministic-v1")
        assert c.execute(
            "SELECT run_id,actual_cost,status FROM reservation_context WHERE id=%s",
            (reservation,),
        ).fetchone() == (run_id, 0, "completed")
        assert c.execute(
            "SELECT prompt_id,rollback_of_id,rollback_reason FROM deployment_context WHERE id=%s",
            (rollback,),
        ).fetchone() == (prompt, deployed, "Restore v1")
        for table, removed in [
            (
                "runs",
                ["project_id", "prompt_id", "provider", "model", "input_variables"],
            ),
            (
                "run_reservations",
                ["project_id", "prompt_id", "run_id", "run_created_at", "actual_cost"],
            ),
            ("deployments", ["prompt_id", "rollback_of_id", "rollback_reason"]),
            ("prompt_versions", ["parent_version_id", "variables", "model_config"]),
        ]:
            columns = {
                r[0]
                for r in c.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
            }
            assert not columns.intersection(removed)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
            c.execute(
                "INSERT INTO deployments(version_id,environment,status,requested_by,activated_at) "
                "VALUES(gen_random_uuid(),'dev','active',%s,CURRENT_TIMESTAMP)",
                (uid,),
            )
        assert c.execute(
            "SELECT email_verified_at IS NOT NULL FROM users WHERE id=%s", (uid,)
        ).fetchone() == (True,)
        assert c.execute(
            "SELECT delete_project(%s,%s,'normalized-deletion')", (project, uid)
        ).fetchone() == (True,)
        assert c.execute(
            "SELECT count(*) FROM projects WHERE id=%s", (project,)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM runs WHERE id=%s", (run_id,)
        ).fetchone() == (0,)

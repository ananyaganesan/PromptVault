"""Keep legacy history readable while blocking removed providers in SQL and HTTP."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.db.migrations import (
    apply_migrations,
    discover_migrations,
    migrate_database,
)
from api.app.main import create_app
from api.app.security import hash_password
from tests.database.test_migration_upgrade import temporary_database_url

__all__ = ["temporary_database_url"]
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_gemini_upgrade_preserves_history_and_rejects_removed_provider_writes(
    temporary_database_url: str,
) -> None:
    migrations = discover_migrations(ROOT / "db/migrations")
    with psycopg.connect(temporary_database_url) as c:
        apply_migrations(c, [migration for migration in migrations if migration.version <= 30])
    with psycopg.connect(temporary_database_url) as c:
        # Reproduce a v030 account; current demo seeds require later role and approval DDL.
        admin = c.execute(
            "INSERT INTO users(email,display_name,password_hash,role,email_verified_at) "
            "VALUES('admin@promptvault.dev','Legacy Admin',%s,'admin',CURRENT_TIMESTAMP) "
            "RETURNING id",
            (hash_password("AdminDemo2026!"),),
        ).fetchone()[0]
        pid = c.execute(
            "INSERT INTO projects(name,key,owner_id) VALUES('Legacy',%s,%s) RETURNING id",
            ("legacy-" + uuid4().hex, admin),
        ).fetchone()[0]
        prompt = c.execute(
            "INSERT INTO prompts(project_id,name,key) VALUES(%s,'Legacy','legacy') RETURNING id",
            (pid,),
        ).fetchone()[0]
        version = c.execute(
            "INSERT INTO prompt_versions(prompt_id,version_number,template_body,commit_message,created_by,provider,model,max_output_tokens) VALUES(%s,1,'Hello','Historical',%s,'mock','deterministic-v1',100) RETURNING id",
            (prompt, admin),
        ).fetchone()[0]
        key = c.execute(
            "INSERT INTO provider_keys(provider,alias,encrypted_secret,created_by) VALUES('groq','historical-key',%s,%s) RETURNING id",
            (b"not-a-real-key", admin),
        ).fetchone()[0]
    assert [
        m.version
        for m in migrate_database(temporary_database_url, ROOT / "db/migrations")
    ] == [migration.version for migration in migrations if migration.version > 30]
    with psycopg.connect(temporary_database_url) as c:
        assert c.execute(
            "SELECT role,is_approved,email_verified_at IS NOT NULL FROM users WHERE id=%s",
            (admin,),
        ).fetchone() == ("super_admin", True, True)
        assert (
            c.execute(
                "SELECT model_config FROM version_context WHERE id=%s", (version,)
            ).fetchone()[0]["provider"]
            == "mock"
        )
        assert c.execute(
            "SELECT deactivated_at IS NOT NULL FROM provider_keys WHERE id=%s", (key,)
        ).fetchone()[0]
        for provider in ("mock", "openrouter", "groq"):
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(
                    "INSERT INTO prompt_versions(prompt_id,version_number,template_body,commit_message,created_by,provider,model,max_output_tokens) VALUES(%s,2,'Denied','Denied',%s,%s,'old-model',100)",
                    (prompt, admin, provider),
                )
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute(
                "INSERT INTO deployments(version_id,environment,status,requested_by,activated_at) VALUES(%s,'dev','active',%s,CURRENT_TIMESTAMP)",
                (version, admin),
            )
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy.engine import URL

    params = conninfo_to_dict(temporary_database_url)
    app_url = URL.create(
        "postgresql",
        username=params.get("user"),
        password=params.get("password"),
        host=params.get("host"),
        port=int(params.get("port", "5432")),
        database=params["dbname"],
    ).render_as_string(hide_password=False)
    settings = Settings(
        _env_file=None,
        environment="development",
        database_url=app_url,
        secret_key="isolated-gemini-upgrade-test-secret",
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
        )
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        read = client.get(f"/api/v1/versions/{version}", headers=headers)
        assert (
            read.status_code == 200
            and read.json()["model_config"]["provider"] == "mock"
        )
        execute = client.post(
            "/api/v1/runs",
            headers=headers,
            json={"version_id": str(version), "variables": {}},
        )
        assert (
            execute.status_code == 422 and execute.json()["code"] == "validation_error"
        )
        assert client.get("/api/v1/runs", headers=headers).json()["total"] == 0
        assert (
            client.get("/api/v1/admin/provider-keys", headers=headers).json()["total"]
            == 0
        )

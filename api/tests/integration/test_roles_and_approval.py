"""Three-role boundaries with real PostgreSQL and loopback-only email delivery."""

import importlib.util
import json
import re
import socketserver
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
import pytest
from api.app.main import create_app
from api.app.security import hash_one_time_token
from fastapi.testclient import TestClient
from tests.auth_support import create_verified_test_user
from tests.release_support import validated_deployment


@pytest.mark.database
def test_roles_approval_and_session_revocation(
    test_settings, seeded_database_url, tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "local_smtp_capture",
        Path(__file__).resolve().parents[3] / "scripts/run-local-auth-acceptance.py",
    )
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    monkeypatch.setenv("E2E_MAILBOX_DIR", str(tmp_path))
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), capture.MailCapture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = test_settings.model_copy(
        update={
            "database_url": seeded_database_url,
            "smtp_host": "127.0.0.1",
            "smtp_port": server.server_address[1],
            "smtp_from_email": "local@example.com",
            "smtp_starttls": False,
        }
    )

    def login(client, email, password="CorrectHorse2026!"):
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})

    def headers(response):
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    try:
        with TestClient(create_app(settings)) as client:
            root = headers(login(client, "admin@promptvault.dev", "AdminDemo2026!"))
            assert client.get("/api/v1/auth/me", headers=root).json()["role"] == "super_admin"
            admin_user, old_headers = create_verified_test_user(client, "approval-admin")
            promoted = client.patch(
                f"/api/v1/admin/users/{admin_user['id']}", headers=root, json={"role": "admin"}
            )
            assert promoted.status_code == 200, promoted.text
            assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
            admin = headers(login(client, admin_user["email"]))
            for endpoint in (
                "maintenance",
                "provider-keys",
                "audit",
                "dashboard",
                "model-pricing",
                "runs",
                "budgets",
            ):
                assert client.get(f"/api/v1/admin/{endpoint}", headers=admin).status_code == 403
            for endpoint in ("refresh-views", "create-next-partition"):
                assert (
                    client.post(f"/api/v1/admin/maintenance/{endpoint}", headers=admin).status_code
                    == 403
                )
            assert client.get("/api/v1/admin/maintenance", headers=root).status_code == 200

            email = f"approval-{uuid4().hex}@example.com"
            payload = {
                "email": email,
                "display_name": "Pending Person",
                "password": "CorrectHorse2026!",
            }
            assert (
                client.post(
                    "/api/v1/auth/register", json=payload | {"role": "super_admin"}
                ).status_code
                == 422
            )
            assert (
                client.post(
                    "/api/v1/auth/register", json=payload | {"is_approved": True}
                ).status_code
                == 422
            )
            assert client.post("/api/v1/auth/register", json=payload).status_code == 202
            assert client.post("/api/v1/auth/register", json=payload).status_code == 409
            mail = json.loads(next(tmp_path.glob("*.json")).read_text())
            token = parse_qs(urlsplit(re.search(r"https?://\S+", mail["text"]).group()).query)[
                "token"
            ][0]
            with psycopg.connect(seeded_database_url) as db:
                row = db.execute(
                    "SELECT u.id,u.role,u.is_approved,t.token_hash,t.expires_at-t.created_at "
                    "FROM users u JOIN email_verification_tokens t ON t.user_id=u.id "
                    "WHERE u.email=%s",
                    (email,),
                ).fetchone()
            target = str(row[0])
            assert row[1:4] == ("user", False, hash_one_time_token(token))
            assert 1790 <= row[4].total_seconds() <= 1810
            assert (
                client.patch(
                    f"/api/v1/admin/users/{target}", headers=admin, json={"is_approved": True}
                ).status_code
                == 409
            )
            assert login(client, email).json()["code"] == "email_unverified"
            assert (
                client.post(
                    "/api/v1/auth/email-verification/resend", json={"email": email}
                ).status_code
                == 429
            )
            assert (
                client.post(
                    "/api/v1/auth/email-verification/confirm", json={"token": token}
                ).status_code
                == 204
            )
            assert (
                client.post(
                    "/api/v1/auth/email-verification/confirm", json={"token": token}
                ).status_code
                == 400
            )
            pending = login(client, email)
            assert pending.status_code == 403 and pending.json()["code"] == "approval_pending"
            assert (
                client.get("/api/v1/admin/users", headers=admin, params={"search": email}).json()[
                    "items"
                ][0]["is_approved"]
                is False
            )
            assert (
                client.patch(
                    f"/api/v1/admin/users/{target}", headers=admin, json={"is_approved": True}
                ).status_code
                == 200
            )
            user = headers(login(client, email))
            assert client.get("/api/v1/admin/users", headers=user).status_code == 403
            for target_id in (target, admin_user["id"]):
                assert (
                    client.patch(
                        f"/api/v1/admin/users/{target_id}",
                        headers=admin,
                        json={"role": "super_admin"},
                    ).status_code
                    == 403
                )
            root_id = client.get("/api/v1/auth/me", headers=root).json()["id"]
            assert (
                client.patch(
                    f"/api/v1/admin/users/{root_id}", headers=admin, json={"is_active": False}
                ).status_code
                == 403
            )
            assert (
                client.patch(
                    f"/api/v1/admin/users/{target}", headers=admin, json={"is_active": False}
                ).status_code
                == 200
            )
            assert client.get("/api/v1/auth/me", headers=user).status_code == 401
            assert login(client, email).json()["code"] == "inactive_user"
            assert (
                client.patch(
                    f"/api/v1/admin/users/{target}", headers=admin, json={"is_active": True}
                ).status_code
                == 200
            )
            user = headers(login(client, email))
            assert (
                client.patch(
                    f"/api/v1/admin/users/{target}", headers=admin, json={"is_approved": False}
                ).status_code
                == 200
            )
            assert client.get("/api/v1/auth/me", headers=user).status_code == 401
            assert login(client, email).json()["code"] == "approval_pending"

            # Database maintenance checks the current role inside PostgreSQL too.
            with (
                psycopg.connect(seeded_database_url) as db,
                pytest.raises(psycopg.errors.InsufficientPrivilege),
            ):
                db.execute(
                    "SELECT admin_refresh_reporting_views(%s, 'role-test')", (admin_user["id"],)
                )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.database
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_admin_reviews_deployment_without_system_access(
    test_settings, seeded_database_url, decision
):
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    with TestClient(create_app(settings)) as client:
        root_session = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
        )
        assert root_session.status_code == 200
        root = {"Authorization": f"Bearer {root_session.json()['access_token']}"}
        account, _ = create_verified_test_user(client, "deployment-admin")
        assert (
            client.patch(
                f"/api/v1/admin/users/{account['id']}", headers=root, json={"role": "admin"}
            ).status_code
            == 200
        )
        session = client.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": "CorrectHorse2026!"}
        )
        admin = {"Authorization": f"Bearer {session.json()['access_token']}"}
        project = client.post(
            "/api/v1/projects",
            headers=root,
            json={"name": "Approval test", "key": f"approval-{uuid4().hex}"},
        )
        assert project.status_code == 201, project.text
        prompt = client.post(
            f"/api/v1/projects/{project.json()['id']}/prompts",
            headers=root,
            json={
                "key": "review-test",
                "name": "Review test",
                "template_body": "Hello {{name}}",
                "model_config": {
                    "provider": "gemini",
                    "model": "gemini-3.5-flash-lite",
                    "max_output_tokens": 100,
                },
                "commit_message": "Initial",
            },
        )
        assert prompt.status_code == 201, prompt.text
        deployment = validated_deployment(
            client,
            headers=root,
            json={"version_id": prompt.json()["latest_version"]["id"], "environment": "prod"},
        )
        assert deployment.status_code == 201, deployment.text
        deployment_id = deployment.json()["id"]
        queue = client.get("/api/v1/admin/deployments/pending", headers=admin)
        assert queue.status_code == 200
        assert any(item["id"] == deployment_id for item in queue.json()["items"])
        assert (
            client.get(f"/api/v1/admin/deployments/{deployment_id}", headers=admin).status_code
            == 200
        )
        reviewed = client.post(
            f"/api/v1/admin/deployments/{deployment_id}/{decision}",
            headers=admin,
            json={"review_note": "Local review"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == ("active" if decision == "approve" else "rejected")
        assert client.get("/api/v1/admin/maintenance", headers=admin).status_code == 403


@pytest.mark.database
def test_admin_can_roll_back_without_project_membership(test_settings, seeded_database_url):
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    with TestClient(create_app(settings)) as client:
        root_session = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"},
        )
        assert root_session.status_code == 200
        root = {"Authorization": f"Bearer {root_session.json()['access_token']}"}
        account, _ = create_verified_test_user(client, "rollback-admin")
        assert (
            client.patch(
                f"/api/v1/admin/users/{account['id']}", headers=root, json={"role": "admin"}
            ).status_code
            == 200
        )
        login = client.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": "CorrectHorse2026!"}
        )
        admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
        _, regular = create_verified_test_user(client, "rollback-regular")
        project = client.post(
            "/api/v1/projects",
            headers=root,
            json={"name": "Rollback authorization", "key": f"rollback-{uuid4().hex}"},
        )
        assert project.status_code == 201
        model = {"provider": "gemini", "model": "gemini-3.5-flash-lite", "max_output_tokens": 100}
        prompt = client.post(
            f"/api/v1/projects/{project.json()['id']}/prompts",
            headers=root,
            json={
                "key": "rollback-check",
                "name": "Rollback check",
                "template_body": "Stable {{topic}}",
                "model_config": model,
                "commit_message": "Stable version",
            },
        )
        assert prompt.status_code == 201
        prompt_id = prompt.json()["id"]
        first = prompt.json()["latest_version"]["id"]
        second = client.post(
            f"/api/v1/prompts/{prompt_id}/versions",
            headers=root,
            json={
                "parent_version_id": first,
                "template_body": "Updated {{topic}}",
                "model_config": model,
                "commit_message": "Updated version",
            },
        )
        assert second.status_code == 201
        request = validated_deployment(
            client,
            headers=root,
            json={"version_id": second.json()["id"], "environment": "prod"},
        )
        assert request.status_code == 201
        deployment_id = request.json()["id"]
        assert (
            client.post(
                f"/api/v1/admin/deployments/{deployment_id}/approve", headers=admin, json={}
            ).status_code
            == 200
        )
        active = client.get("/api/v1/admin/deployments/active", headers=admin)
        assert active.status_code == 200
        assert any(item["id"] == deployment_id for item in active.json()["items"])
        targets_url = f"/api/v1/admin/deployments/{deployment_id}/rollback-targets"
        targets = client.get(targets_url, headers=admin)
        assert targets.status_code == 200, targets.text
        assert [item["id"] for item in targets.json()["items"]] == [first]
        for url in ("/api/v1/admin/deployments/active", targets_url):
            assert client.get(url, headers=regular).status_code == 403
        rollback_url = f"/api/v1/admin/prompts/{prompt_id}/rollback"
        payload = {"target_version_id": first, "reason": "Restore the stable answer"}
        assert client.post(rollback_url, headers=regular, json=payload).status_code == 403
        assert (
            client.post(rollback_url, headers=admin, json=payload | {"reason": ""}).status_code
            == 422
        )
        assert (
            client.post(
                rollback_url,
                headers=admin,
                json=payload | {"target_version_id": second.json()["id"]},
            ).status_code
            == 409
        )
        rolled_back = client.post(rollback_url, headers=admin, json=payload)
        assert rolled_back.status_code == 201, rolled_back.text
        assert rolled_back.json()["version_id"] == first
        assert rolled_back.json()["rollback_of_id"] == deployment_id
        assert rolled_back.json()["rollback_reason"] == payload["reason"]
        assert client.get(targets_url, headers=admin).status_code == 409
        assert (
            client.get(
                f"/api/v1/admin/deployments/{rolled_back.json()['id']}", headers=admin
            ).status_code
            == 200
        )
        assert client.get("/api/v1/admin/maintenance", headers=admin).status_code == 403
        with psycopg.connect(seeded_database_url) as db:
            db.execute("UPDATE users SET role='user' WHERE id=%s", (account["id"],))
        # Stored procedure independently rejects a role that changed after API authorization.
        with (
            psycopg.connect(seeded_database_url) as db,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            db.execute(
                "SELECT rollback_deployment(%s,%s,%s,%s)",
                (prompt_id, first, account["id"], "Unauthorized direct call"),
            )

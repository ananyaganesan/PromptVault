"""Commit between query execution and row consumption, without timing races."""

import asyncio
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.repositories.admin import AdminRepository
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.prompts import PromptRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.users import UserRepository
from api.app.repositories.versions import VersionRepository
from api.app.services.prompt_versioning import PromptVersioningService
from tests.invitation_support import accept_invitation
from tests.release_support import validated_deployment
from tests.support import create_project, create_prompt, register


@pytest.mark.database
@pytest.mark.parametrize(
    "scope",
    [
        "projects",
        "members",
        "prompts",
        "versions",
        "runs",
        "admin_runs",
        "pending",
        "active",
    ],
)
async def test_page_count_and_rows_share_snapshot_during_concurrent_commit(
    api_client: TestClient, database_url: str, scope: str
) -> None:
    owner, headers = register(api_client, "snapshot-owner")
    member, member_headers = register(api_client, "snapshot-member")
    project = create_project(api_client, headers, label="Snapshot")
    prompt = create_prompt(api_client, headers, project["id"])
    version = prompt["latest_version"]
    assert (
        api_client.post(
            f"/api/v1/projects/{project['id']}/members",
            headers=headers,
            json={"email": member["email"]},
        ).status_code
        == 201
    )
    accept_invitation(api_client, str(member["email"]), member_headers)
    run_payload = {
        "version_id": version["id"],
        "variables": {"name": "Snapshot", "order_id": "1"},
    }
    assert (
        api_client.post("/api/v1/runs", headers=headers, json=run_payload).status_code
        == 201
    )
    deployments = {}
    for environment in ("prod", "dev"):
        response = validated_deployment(
            api_client,
            "/api/v1/deployments",
            headers=headers,
            json={"version_id": version["id"], "environment": environment},
        )
        assert response.status_code == 201
        deployments[environment] = response.json()

    project_id, prompt_id, actor_id = (
        UUID(str(project["id"])),
        UUID(prompt["id"]),
        UUID(str(owner["id"])),
    )

    def mutate() -> None:
        if scope == "projects":
            create_project(api_client, headers, label="Snapshot")
        elif scope == "members":
            assert (
                api_client.delete(
                    f"/api/v1/projects/{project_id}/members/{member['id']}",
                    headers=headers,
                ).status_code
                == 204
            )
        elif scope == "prompts":
            create_prompt(api_client, headers, project_id, key="second-reply")
        elif scope == "versions":
            assert (
                api_client.post(
                    f"/api/v1/prompts/{prompt_id}/versions",
                    headers=headers,
                    json={
                        "parent_version_id": version["id"],
                        "template_body": "Second",
                        "model_config": version["model_config"],
                        "commit_message": "Second",
                    },
                ).status_code
                == 201
            )
        elif scope in ("runs", "admin_runs"):
            assert (
                api_client.post(
                    "/api/v1/runs", headers=headers, json=run_payload
                ).status_code
                == 201
            )
        elif scope == "pending":
            assert (
                api_client.post(
                    f"/api/v1/deployments/{deployments['prod']['id']}/cancel",
                    headers=headers,
                ).status_code
                == 200
            )
        else:
            assert (
                validated_deployment(
                    api_client,
                    "/api/v1/deployments",
                    headers=headers,
                    json={"version_id": version["id"], "environment": "dev"},
                ).status_code
                == 201
            )

    from api.app.db.pool import create_pool

    pool = create_pool(api_client.app.state.settings)
    await pool.open()
    connection_context = pool.connection()
    connection = await connection_context.__aenter__()

    class CommitAfterFirstRead:
        calls = 0

        async def execute(self, query: Any, parameters: Any = None) -> Any:
            cursor = await connection.execute(query, parameters)
            self.calls += 1
            if self.calls == 1:
                await asyncio.to_thread(mutate)
            return cursor

    async def read(raw: Any, page: int = 1) -> tuple[list[Any], int]:
        shared = cast(psycopg.AsyncConnection[dict[str, Any]], raw)
        if scope == "projects":
            return await ProjectRepository(shared).list_for_user(
                user_id=actor_id,
                role="user",
                search=None,
                page=page,
                page_size=100,
                sort="name",
                direction="asc",
            )
        if scope == "members":
            return await ProjectRepository(shared).list_members(
                project_id, page=page, page_size=100
            )
        if scope == "prompts":
            return await PromptRepository(shared).list_for_project(
                project_id,
                search=None,
                page=page,
                page_size=100,
                sort="key",
                direction="asc",
            )
        if scope == "versions":
            return await VersionRepository(shared).list_for_prompt(
                prompt_id,
                page=page,
                page_size=100,
                sort="version_number",
                direction="desc",
            )
        if scope == "admin_runs":
            return await AdminRepository(shared).list_runs(
                user_id=actor_id,
                project_id=project_id,
                prompt_id=None,
                status=None,
                model=None,
                created_from=None,
                created_to=None,
                search="reply",
                page=page,
                page_size=100,
            )
        if scope == "runs":
            return await RunRepository(shared).list_scoped(
                user_id=actor_id,
                role="user",
                project_id=project_id,
                prompt_id=None,
                version_id=None,
                status=None,
                model=None,
                created_from=None,
                created_to=None,
                search="reply",
                page=page,
                page_size=100,
            )
        return await DeploymentRepository(shared).list_scoped(
            user_id=actor_id,
            role="user",
            project_id=project_id,
            prompt_id=None,
            environment="prod" if scope == "pending" else "dev",
            status="pending" if scope == "pending" else "active",
            page=page,
            page_size=100,
        )

    try:
        proxy = CommitAfterFirstRead()
        items, total = await read(proxy)
        expected = (
            2 if scope == "members" else 3 if scope in ("runs", "admin_runs") else 1
        )
        assert total == len(items) == expected
        assert proxy.calls == 1
        current, current_total = await read(connection)
        assert current_total == len(current)
        if scope == "active":
            assert items[0].id != current[0].id
        else:
            assert current_total != total
        empty, empty_total = await read(connection, page=99)
        assert empty == []
        assert empty_total == current_total
    finally:
        await connection_context.__aexit__(None, None, None)
        await pool.close()


@pytest.mark.database
def test_dashboard_metrics_trend_and_activity_share_snapshot(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, headers = register(api_client, "dashboard-snapshot")
    project = create_project(api_client, headers)
    prompt = create_prompt(api_client, headers, project["id"])
    payload = {
        "version_id": prompt["latest_version"]["id"],
        "variables": {"name": "Snapshot", "order_id": "1"},
    }
    assert (
        api_client.post("/api/v1/runs", headers=headers, json=payload).status_code
        == 201
    )
    original = RunRepository.personal_metrics
    committed = False

    async def metrics(repository: RunRepository, **kwargs: Any) -> Any:
        nonlocal committed
        result = await original(repository, **kwargs)
        if not committed:
            committed = True
            response = await asyncio.to_thread(
                api_client.post, "/api/v1/runs", headers=headers, json=payload
            )
            assert response.status_code == 201
        return result

    monkeypatch.setattr(RunRepository, "personal_metrics", metrics)
    response = api_client.get("/api/v1/dashboard/me", headers=headers)
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["run_count"] == snapshot["completed_run_count"] == 1
    assert len(snapshot["recent_runs"]) == 1
    assert sum(point["run_count"] for point in snapshot["cost_trend"]) == 1
    response = api_client.get("/api/v1/dashboard/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["run_count"] == len(response.json()["recent_runs"]) == 2


@pytest.mark.database
@pytest.mark.parametrize("view", ["prompt", "lineage"])
async def test_detail_reads_hold_membership_until_transaction_finishes(
    api_client: TestClient,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    view: str,
) -> None:
    _, headers = register(api_client, "detail-owner")
    member, member_headers = register(api_client, "detail-member")
    project = create_project(api_client, headers)
    prompt = create_prompt(api_client, headers, project["id"])
    assert (
        api_client.post(
            f"/api/v1/projects/{project['id']}/members",
            headers=headers,
            json={"email": member["email"]},
        ).status_code
        == 201
    )
    accept_invitation(api_client, str(member["email"]), member_headers)
    from api.app.db.pool import create_pool

    pool = create_pool(api_client.app.state.settings)
    await pool.open()
    connection_context = pool.connection()
    connection = await connection_context.__aenter__()
    remover = await psycopg.AsyncConnection.connect(database_url, row_factory=dict_row)
    original = (
        PromptRepository.get_metadata_scoped
        if view == "prompt"
        else VersionRepository.lineage
    )
    attempts = 0

    async def attempt_revocation(repository: Any, *args: Any) -> Any:
        nonlocal attempts
        attempts += 1
        with pytest.raises(psycopg.errors.LockNotAvailable):
            async with remover.transaction():
                await remover.execute("SET LOCAL lock_timeout = '100ms'")
                await remover.execute(
                    "DELETE FROM project_members WHERE project_id=%s AND user_id=%s",
                    (project["id"], member["id"]),
                )
        return await original(repository, *args)

    if view == "prompt":
        monkeypatch.setattr(PromptRepository, "get_metadata_scoped", attempt_revocation)
    else:
        monkeypatch.setattr(VersionRepository, "lineage", attempt_revocation)
    try:
        async with connection.transaction():
            actor = await UserRepository(connection).get_by_id(UUID(str(member["id"])))
            assert actor is not None
            service = PromptVersioningService(
                PromptRepository(connection),
                VersionRepository(connection),
                ProjectRepository(connection),
                "detail-snapshot-test",
            )
            if view == "prompt":
                await service.get_prompt(UUID(prompt["id"]), actor)
            else:
                await service.lineage(UUID(prompt["latest_version"]["id"]), actor)
            assert attempts == 1
        async with remover.transaction():
            deleted = await remover.execute(
                "DELETE FROM project_members WHERE project_id=%s AND user_id=%s",
                (project["id"], member["id"]),
            )
            assert deleted.rowcount == 1
        path = (
            f"/api/v1/prompts/{prompt['id']}"
            if view == "prompt"
            else f"/api/v1/versions/{prompt['latest_version']['id']}/lineage"
        )
        assert api_client.get(path, headers=member_headers).status_code == 404
    finally:
        await connection_context.__aexit__(None, None, None)
        await pool.close()
        await remover.close()

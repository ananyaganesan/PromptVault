"""Project creation remains restricted to administrators."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from api.app.config import Settings
from api.app.errors import AppError
from api.app.repositories.users import UserRecord
from api.app.schemas.projects import ProjectCreate
from api.app.services.projects import ProjectService


@pytest.mark.asyncio
async def test_regular_user_cannot_create_project(test_settings: Settings) -> None:
    repository = AsyncMock()
    service = ProjectService(repository, AsyncMock(), "request-id", test_settings)
    actor = UserRecord(
        id=uuid4(),
        email="user@example.com",
        display_name="Regular User",
        password_hash="unused",
        role="user",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    with pytest.raises(AppError) as raised:
        await service.create(
            ProjectCreate(name="Forbidden", key="forbidden", description=None), actor
        )

    assert raised.value.status_code == 403
    assert raised.value.code == "forbidden"
    repository.create.assert_not_awaited()
    repository.set_audit_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_regular_user_cannot_delete_project(test_settings: Settings) -> None:
    repository = AsyncMock()
    service = ProjectService(repository, AsyncMock(), "request-id", test_settings)
    actor = UserRecord(
        id=uuid4(),
        email="user@example.com",
        display_name="Regular User",
        password_hash="unused",
        role="user",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    with pytest.raises(AppError) as raised:
        await service.delete(uuid4(), actor)

    assert raised.value.status_code == 403
    assert raised.value.code == "forbidden"
    repository.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_deletes_project_or_receives_not_found(test_settings: Settings) -> None:
    repository = AsyncMock()
    service = ProjectService(repository, AsyncMock(), "request-id", test_settings)
    actor = UserRecord(
        id=uuid4(),
        email="admin@example.com",
        display_name="Administrator",
        password_hash="unused",
        role="admin",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    project_id = uuid4()

    repository.delete.return_value = True
    await service.delete(project_id, actor)
    repository.delete.assert_awaited_once_with(project_id, actor.id, "request-id")

    repository.delete.reset_mock()
    repository.delete.return_value = False
    with pytest.raises(AppError) as raised:
        await service.delete(project_id, actor)
    assert raised.value.status_code == 404
    assert raised.value.code == "not_found"

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from api.app.errors import AppError
from api.app.repositories.users import UserRecord
from api.app.schemas.admin import AdminUserUpdate
from api.app.services.admin import AdminGovernanceService
from psycopg.errors import CheckViolation, InsufficientPrivilege


def admin_actor() -> UserRecord:
    return UserRecord(
        id=uuid4(),
        email="admin@example.com",
        display_name="Admin",
        password_hash="unused",
        role="super_admin",
        is_active=True,
        is_approved=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_user_transition_maps_concurrent_authorization_change() -> None:
    repository = MagicMock()
    repository.set_audit_context = AsyncMock()
    repository.update_user = AsyncMock(
        side_effect=InsufficientPrivilege("admin_required")
    )
    service = AdminGovernanceService(repository, "request-id", "encryption-key")

    with pytest.raises(AppError) as captured:
        await service.update_user(uuid4(), AdminUserUpdate(is_active=False), admin_actor())

    assert captured.value.status_code == 403
    assert captured.value.code == "forbidden"


@pytest.mark.asyncio
async def test_user_transition_rejects_peer_admin_demotion() -> None:
    repository = MagicMock()
    repository.set_audit_context = AsyncMock()
    repository.update_user = AsyncMock(
        side_effect=CheckViolation("admin_peer_demotion")
    )
    service = AdminGovernanceService(repository, "request-id", "encryption-key")

    with pytest.raises(AppError) as captured:
        await service.update_user(
            uuid4(), AdminUserUpdate(role="user"), admin_actor()
        )

    assert captured.value.status_code == 403
    assert captured.value.code == "forbidden"
    assert captured.value.message == (
        "A Super Admin cannot change another Super Admin to User"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["refresh_views", "create_next_partition"])
async def test_maintenance_maps_concurrent_authorization_change(operation: str) -> None:
    repository = MagicMock()
    setattr(
        repository,
        operation,
        AsyncMock(side_effect=InsufficientPrivilege("admin_required")),
    )
    service = AdminGovernanceService(repository, "request-id", "encryption-key")

    with pytest.raises(AppError) as captured:
        await getattr(service, operation)(admin_actor())

    assert captured.value.status_code == 403
    assert captured.value.code == "forbidden"

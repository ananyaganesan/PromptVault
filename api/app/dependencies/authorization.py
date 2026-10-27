"""Reusable role and project-scope authorization dependencies."""

from typing import Annotated
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.errors import AppError
from api.app.repositories.users import UserRecord, UserRepository
from fastapi import Depends


async def require_admin(current_user: CurrentUser) -> UserRecord:
    if current_user.role not in ("admin", "super_admin"):
        raise AppError(403, "forbidden", "Admin access is required")
    return current_user


Admin = Annotated[UserRecord, Depends(require_admin)]


async def require_super_admin(current_user: CurrentUser) -> UserRecord:
    if current_user.role != "super_admin":
        raise AppError(403, "forbidden", "Super Admin access is required")
    return current_user


SuperAdmin = Annotated[UserRecord, Depends(require_super_admin)]


async def require_project_member(
    project_id: UUID,
    current_user: CurrentUser,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> UserRecord:
    if current_user.role == "super_admin":
        return current_user
    if not await UserRepository(connection).is_project_member(current_user.id, project_id):
        raise AppError(403, "forbidden", "Project membership is required")
    return current_user


ProjectMember = Annotated[UserRecord, Depends(require_project_member)]


async def require_project_owner(
    project_id: UUID,
    current_user: CurrentUser,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> UserRecord:
    if current_user.role == "super_admin":
        return current_user
    if not await UserRepository(connection).is_project_owner(current_user.id, project_id):
        raise AppError(403, "forbidden", "Project ownership is required")
    return current_user


ProjectOwner = Annotated[UserRecord, Depends(require_project_owner)]

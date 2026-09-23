"""Project and membership use cases."""

from uuid import UUID

from api.app.errors import AppError
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.users import UserRecord, UserRepository
from api.app.schemas.common import Page
from api.app.schemas.projects import (
    ProjectCreate,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from psycopg.errors import UniqueViolation


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        users: UserRepository,
        request_id: str,
    ) -> None:
        self.repository = repository
        self.users = users
        self.request_id = request_id

    async def create(self, payload: ProjectCreate, actor: UserRecord) -> ProjectResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            project_id = await self.repository.create(
                name=payload.name,
                key=payload.key,
                description=payload.description,
                owner_id=actor.id,
            )
        except UniqueViolation as exc:
            raise AppError(409, "duplicate_key", "Project key is already in use") from exc
        return await self.require_project(project_id)

    async def list(
        self,
        actor: UserRecord,
        *,
        search: str | None,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> Page[ProjectResponse]:
        items, total = await self.repository.list_for_user(
            user_id=actor.id,
            role=actor.role,
            search=search.strip() if search else None,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def require_project(self, project_id: UUID) -> ProjectResponse:
        project = await self.repository.get(project_id)
        if project is None:
            raise AppError(404, "not_found", "Project was not found")
        return project

    async def require_member_project(
        self, project_id: UUID, actor: UserRecord
    ) -> ProjectResponse:
        if not await self.repository.lock_member_access(project_id, actor.id, actor.role):
            if actor.role == "admin":
                raise AppError(404, "not_found", "Project was not found")
            raise AppError(403, "forbidden", "Project membership is required")
        return await self.require_project(project_id)

    async def update(
        self, project_id: UUID, payload: ProjectUpdate, actor: UserRecord
    ) -> ProjectResponse:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        await self.repository.set_audit_context(actor.id, self.request_id)
        updated = await self.repository.update(
            project_id,
            name_set="name" in payload.model_fields_set,
            name=payload.name,
            description_set="description" in payload.model_fields_set,
            description=payload.description,
        )
        if not updated:
            raise AppError(404, "not_found", "Project was not found")
        return await self.require_project(project_id)

    async def list_members(
        self, project_id: UUID, actor: UserRecord, *, page: int, page_size: int
    ) -> Page[ProjectMemberResponse]:
        await self.require_member_project(project_id, actor)
        items, total = await self.repository.list_members(
            project_id, page=page, page_size=page_size
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def add_member(
        self, project_id: UUID, email: str, actor: UserRecord
    ) -> ProjectMemberResponse:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            raise AppError(404, "not_found", "Active user was not found")
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            await self.repository.add_member(project_id, user.id, actor.id)
        except UniqueViolation as exc:
            raise AppError(409, "conflict", "User is already a project member") from exc
        member = await self.repository.get_member(project_id, user.id)
        if member is None:
            raise RuntimeError("created project member was not returned")
        return member

    async def remove_member(
        self, project_id: UUID, user_id: UUID, actor: UserRecord
    ) -> None:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        project = await self.require_project(project_id)
        if project.owner.id == user_id:
            raise AppError(409, "conflict", "Project owner cannot be removed")
        await self.repository.set_audit_context(actor.id, self.request_id)
        if not await self.repository.remove_member(project_id, user_id):
            raise AppError(404, "not_found", "Project member was not found")

"""Project and membership use cases."""

from __future__ import annotations

import builtins
from secrets import token_urlsafe
from uuid import UUID

from api.app.config import Settings
from api.app.email import EmailDeliveryError, send_project_invitation_email
from api.app.errors import AppError
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.users import UserRecord, UserRepository
from api.app.schemas.common import Page
from api.app.schemas.projects import (
    ProjectCreate,
    ProjectInvitationResponse,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from api.app.security import hash_one_time_token
from psycopg.errors import UniqueViolation
from starlette.concurrency import run_in_threadpool


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        users: UserRepository,
        request_id: str,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.users = users
        self.request_id = request_id
        self.settings = settings

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

    async def require_member_project(self, project_id: UUID, actor: UserRecord) -> ProjectResponse:
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
    ) -> ProjectInvitationResponse:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            raise AppError(
                404, "not_found", "Active user was not found; ask them to register first"
            )
        if await self.repository.get_member(project_id, user.id):
            raise AppError(409, "conflict", "User is already a project member")
        project = await self.require_project(project_id)
        token = token_urlsafe(32)
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            invitation_id = await self.repository.create_invitation(
                project_id, user.id, actor.id, hash_one_time_token(token)
            )
        except UniqueViolation as exc:
            raise AppError(
                409, "conflict", "An invitation is already pending for this user"
            ) from exc
        try:
            await run_in_threadpool(
                send_project_invitation_email,
                self.settings,
                user.email,
                token,
                project.name,
                actor.display_name,
            )
        except EmailDeliveryError as exc:
            raise AppError(
                503, "email_delivery_unavailable", "Invitation email could not be delivered"
            ) from exc
        invitations = await self.repository.list_invitations(project_id)
        return next(item for item in invitations if item.id == invitation_id)

    async def list_invitations(
        self, project_id: UUID, actor: UserRecord
    ) -> builtins.list[ProjectInvitationResponse]:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        return await self.repository.list_invitations(project_id)

    async def revoke_invitation(
        self, project_id: UUID, invitation_id: UUID, actor: UserRecord
    ) -> None:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        await self.repository.set_audit_context(actor.id, self.request_id)
        if not await self.repository.revoke_invitation(project_id, invitation_id):
            raise AppError(404, "not_found", "Pending invitation was not found")

    async def accept_invitation(self, token: str, actor: UserRecord) -> ProjectResponse:
        invitation = await self.repository.lock_invitation(hash_one_time_token(token))
        if (
            invitation is None
            or invitation["accepted_at"]
            or invitation["revoked_at"]
            or not invitation["unexpired"]
        ):
            raise AppError(
                410, "invalid_invitation", "Invitation is expired, cancelled or already accepted"
            )
        if invitation["user_id"] != actor.id:
            raise AppError(403, "forbidden", "Sign in to the account that received this invitation")
        inviter = await self.users.get_by_id(invitation["invited_by"])
        if (
            inviter is None
            or not inviter.is_active
            or not await self.repository.lock_owner_access(
                invitation["project_id"], inviter.id, inviter.role
            )
        ):
            raise AppError(
                410, "invalid_invitation", "The inviter can no longer grant project access"
            )
        await self.repository.set_audit_context(actor.id, self.request_id)
        # Direct setup memberships may exist in historical/demo data.
        if not await self.repository.get_member(invitation["project_id"], actor.id):
            await self.repository.add_member(invitation["project_id"], actor.id, inviter.id)
        await self.repository.consume_invitation(invitation["id"])
        return await self.require_project(invitation["project_id"])

    async def remove_member(self, project_id: UUID, user_id: UUID, actor: UserRecord) -> None:
        if not await self.repository.lock_owner_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        project = await self.require_project(project_id)
        if project.owner.id == user_id:
            raise AppError(409, "conflict", "Project owner cannot be removed")
        await self.repository.set_audit_context(actor.id, self.request_id)
        if not await self.repository.remove_member(project_id, user_id):
            raise AppError(404, "not_found", "Project member was not found")

"""Prompt metadata and immutable version use cases."""

import re
from uuid import UUID

from api.app.errors import AppError
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.prompts import PromptRepository
from api.app.repositories.users import UserRecord
from api.app.repositories.versions import VersionRepository
from api.app.schemas.common import Page
from api.app.schemas.prompts import (
    PromptCreate,
    PromptResponse,
    PromptSummaryResponse,
    PromptUpdate,
)
from api.app.schemas.versions import (
    ModelConfigurationDiff,
    PromptVersionCreate,
    PromptVersionResponse,
    TemplateDiff,
    VariableDiff,
    VersionDiffResponse,
    VersionLineageResponse,
)
from psycopg.errors import CheckViolation, UniqueViolation

_ANY_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}")
_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def extract_variables(template_body: str) -> list[str]:
    variables: list[str] = []
    seen: set[str] = set()
    for raw in _ANY_PLACEHOLDER.findall(template_body):
        candidate = raw.strip()
        if _VARIABLE_NAME.fullmatch(candidate) is None:
            raise AppError(
                422,
                "validation_error",
                "Template contains an invalid variable name",
                field_errors={"body.template_body": [f"Invalid variable: {candidate}"]},
            )
        if candidate not in seen:
            variables.append(candidate)
            seen.add(candidate)
    return variables


class PromptVersioningService:
    def __init__(
        self,
        prompts: PromptRepository,
        versions: VersionRepository,
        projects: ProjectRepository,
        request_id: str,
    ) -> None:
        self.prompts = prompts
        self.versions = versions
        self.projects = projects
        self.request_id = request_id

    async def _require_prompt_metadata(
        self, prompt_id: UUID, actor: UserRecord
    ) -> dict[str, object]:
        metadata = await self.prompts.get_metadata_scoped(prompt_id, actor.id, actor.role)
        if metadata is None:
            raise AppError(404, "not_found", "Prompt was not found")
        return dict(metadata)

    async def _prompt_response(self, prompt_id: UUID) -> PromptResponse:
        metadata = await self.prompts.get_metadata(prompt_id)
        latest = await self.versions.latest(prompt_id)
        if metadata is None or latest is None:
            raise AppError(404, "not_found", "Prompt was not found")
        return PromptResponse(
            **metadata,
            latest_version=latest,
            active_versions=await self.prompts.get_active_versions(prompt_id),
        )

    async def create_prompt(
        self, project_id: UUID, payload: PromptCreate, actor: UserRecord
    ) -> PromptResponse:
        if not await self.projects.lock_member_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        await self.projects.set_audit_context(actor.id, self.request_id)
        try:
            prompt_id = await self.prompts.create(
                project_id=project_id,
                key=payload.key,
                name=payload.name,
                description=payload.description,
            )
            await self.versions.create(
                prompt_id=prompt_id,
                parent_version_id=None,
                template_body=payload.template_body,
                variables=extract_variables(payload.template_body),
                model_config=payload.model_configuration,
                commit_message=payload.commit_message,
                created_by=actor.id,
            )
        except UniqueViolation as exc:
            raise AppError(409, "duplicate_key", "Prompt key is already in use") from exc
        return await self._prompt_response(prompt_id)

    async def list_prompts(
        self,
        project_id: UUID,
        actor: UserRecord,
        *,
        search: str | None,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> Page[PromptSummaryResponse]:
        if not await self.projects.lock_member_access(project_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Project was not found")
        items, total = await self.prompts.list_for_project(
            project_id,
            search=search.strip() if search else None,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def get_prompt(self, prompt_id: UUID, actor: UserRecord) -> PromptResponse:
        await self._require_prompt_metadata(prompt_id, actor)
        return await self._prompt_response(prompt_id)

    async def update_prompt(
        self,
        prompt_id: UUID,
        payload: PromptUpdate,
        actor: UserRecord,
    ) -> PromptResponse:
        if not await self.prompts.lock_member_access(prompt_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Prompt was not found")
        await self.projects.set_audit_context(actor.id, self.request_id)
        updated = await self.prompts.update(
            prompt_id,
            name_set="name" in payload.model_fields_set,
            name=payload.name,
            description_set="description" in payload.model_fields_set,
            description=payload.description,
        )
        if not updated:
            raise AppError(404, "not_found", "Prompt was not found")
        return await self._prompt_response(prompt_id)

    async def create_version(
        self,
        prompt_id: UUID,
        payload: PromptVersionCreate,
        actor: UserRecord,
    ) -> PromptVersionResponse:
        if not await self.prompts.lock_member_access(prompt_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Prompt was not found")
        await self.projects.set_audit_context(actor.id, self.request_id)
        try:
            return await self.versions.create(
                prompt_id=prompt_id,
                parent_version_id=payload.parent_version_id,
                template_body=payload.template_body,
                variables=extract_variables(payload.template_body),
                model_config=payload.model_configuration,
                commit_message=payload.commit_message,
                created_by=actor.id,
            )
        except CheckViolation as exc:
            raise AppError(409, "conflict", "Parent version is invalid") from exc

    async def list_versions(
        self,
        prompt_id: UUID,
        actor: UserRecord,
        *,
        page: int,
        page_size: int,
        sort: str,
        direction: str,
    ) -> Page[PromptVersionResponse]:
        if not await self.prompts.lock_member_access(prompt_id, actor.id, actor.role):
            raise AppError(404, "not_found", "Prompt was not found")
        items, total = await self.versions.list_for_prompt(
            prompt_id,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def require_version(
        self, version_id: UUID, actor: UserRecord
    ) -> PromptVersionResponse:
        version = await self.versions.get_scoped(version_id, actor.id, actor.role)
        if version is None:
            raise AppError(404, "not_found", "Prompt version was not found")
        return version

    async def diff(
        self,
        version_id: UUID,
        against_id: UUID,
        actor: UserRecord,
    ) -> VersionDiffResponse:
        target = await self.require_version(version_id, actor)
        against = await self.require_version(against_id, actor)
        if target.prompt_id != against.prompt_id:
            raise AppError(409, "conflict", "Versions must belong to the same prompt")
        before_config = against.model_configuration.model_dump()
        after_config = target.model_configuration.model_dump()
        return VersionDiffResponse(
            from_version_id=against.id,
            to_version_id=target.id,
            template_body=TemplateDiff(
                changed=against.template_body != target.template_body,
                before=against.template_body,
                after=target.template_body,
            ),
            variables=VariableDiff(
                added=[value for value in target.variables if value not in against.variables],
                removed=[value for value in against.variables if value not in target.variables],
            ),
            model_config=ModelConfigurationDiff(
                changed_fields=sorted(
                    key for key in before_config if before_config[key] != after_config[key]
                ),
                before=against.model_configuration,
                after=target.model_configuration,
            ),
        )

    async def lineage(self, version_id: UUID, actor: UserRecord) -> VersionLineageResponse:
        await self.require_version(version_id, actor)
        items, cycle_detected = await self.versions.lineage(version_id)
        return VersionLineageResponse(items=items, cycle_detected=cycle_detected)

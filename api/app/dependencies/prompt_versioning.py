"""Prompt/version service dependency wiring."""

from typing import Annotated

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.request_context import get_request_id
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.prompts import PromptRepository
from api.app.repositories.versions import VersionRepository
from api.app.services.prompt_versioning import PromptVersioningService
from fastapi import Depends, Request


def get_prompt_versioning_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> PromptVersioningService:
    return PromptVersioningService(
        PromptRepository(connection),
        VersionRepository(connection),
        ProjectRepository(connection),
        get_request_id(request),
        allow_mock=request.app.state.settings.environment in {"development", "test"},
    )


PromptService = Annotated[PromptVersioningService, Depends(get_prompt_versioning_service)]

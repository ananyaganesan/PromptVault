"""Prompt metadata API models."""

import re
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from api.app.schemas.versions import ModelConfiguration, PromptVersionResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PromptKey = Annotated[str, Field(min_length=1, max_length=63, pattern=_KEY_PATTERN.pattern)]
PromptName = Annotated[str, Field(min_length=1, max_length=160)]


class PromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: PromptKey
    name: PromptName
    description: Annotated[str | None, Field(max_length=4000)] = None
    template_body: Annotated[str, Field(min_length=1, max_length=100_000)]
    model_configuration: ModelConfiguration = Field(alias="model_config")
    commit_message: Annotated[str, Field(min_length=1, max_length=500)]

    @field_validator("name", "template_body", "commit_message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PromptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PromptName | None = None
    description: Annotated[str | None, Field(max_length=4000)] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class PromptSummaryResponse(BaseModel):
    id: UUID
    project_id: UUID
    key: str
    name: str
    description: str | None
    latest_version_number: int
    created_at: datetime
    updated_at: datetime


class PromptResponse(BaseModel):
    id: UUID
    project_id: UUID
    key: str
    name: str
    description: str | None
    latest_version: PromptVersionResponse
    active_versions: dict[str, UUID]
    created_at: datetime
    updated_at: datetime

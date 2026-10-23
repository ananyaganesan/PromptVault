"""Immutable prompt-version API models."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from api.app.providers.policy import ConfiguredProvider
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SavedModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: Annotated[str, Field(min_length=1, max_length=160)]
    temperature: Annotated[float, Field(ge=0, le=2)] = 0
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)]

    @field_validator("provider", "model")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class ModelConfiguration(SavedModelConfiguration):
    provider: ConfiguredProvider


class VersionAuthorResponse(BaseModel):
    id: UUID
    display_name: str


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_version_id: UUID
    template_body: Annotated[str, Field(min_length=1, max_length=100_000)]
    model_configuration: ModelConfiguration = Field(alias="model_config")
    commit_message: Annotated[str, Field(min_length=1, max_length=500)]

    @field_validator("template_body", "commit_message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class PromptVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    prompt_id: UUID
    version_number: int
    parent_version_id: UUID | None
    template_body: str
    variables: list[str]
    model_configuration: SavedModelConfiguration = Field(alias="model_config")
    commit_message: str
    created_by: VersionAuthorResponse
    created_at: datetime


class TemplateDiff(BaseModel):
    changed: bool
    before: str
    after: str


class VariableDiff(BaseModel):
    added: list[str]
    removed: list[str]


class ModelConfigurationDiff(BaseModel):
    changed_fields: list[str]
    before: SavedModelConfiguration
    after: SavedModelConfiguration


class VersionDiffResponse(BaseModel):
    from_version_id: UUID
    to_version_id: UUID
    template_body: TemplateDiff
    variables: VariableDiff
    model_configuration: ModelConfigurationDiff = Field(alias="model_config")


class VersionLineageResponse(BaseModel):
    items: list[PromptVersionResponse]
    cycle_detected: bool

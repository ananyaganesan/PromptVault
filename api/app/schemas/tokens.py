"""Project-scoped runtime token and Serve API models."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from api.app.schemas.deployments import DeploymentEnvironment
from api.app.schemas.versions import ModelConfiguration
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name: Annotated[str, Field(min_length=1, max_length=120)]
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return value


class ApiTokenResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    token_prefix: str
    created_by: UUID
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreatedResponse(ApiTokenResponse):
    token: str


class ServedVersion(BaseModel):
    id: UUID
    version_number: int


class ServePromptResponse(BaseModel):
    project_id: UUID
    prompt_key: str
    environment: DeploymentEnvironment
    version: ServedVersion
    template_body: str
    variables: list[str]
    model_configuration: ModelConfiguration = Field(alias="model_config")
    activated_at: datetime

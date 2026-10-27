"""Deployment lifecycle API models."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from api.app.schemas.release_validation import ReleaseValidationResponse
from api.app.schemas.runs import RunResponse
from api.app.schemas.versions import PromptVersionResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

DeploymentEnvironment = Literal["dev", "staging", "prod"]
DeploymentStatus = Literal[
    "pending", "active", "rejected", "cancelled", "superseded", "rolled_back"
]


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID
    validation_id: UUID | None = None
    environment: DeploymentEnvironment
    request_note: Annotated[str | None, Field(max_length=2_000)] = None

    @field_validator("request_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DeploymentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_note: Annotated[str | None, Field(max_length=2_000)] = None

    @field_validator("review_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DeploymentReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_note: Annotated[str, Field(min_length=1, max_length=2_000)]

    @field_validator("review_note")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class RollbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_version_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=2_000)]

    @field_validator("reason")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class DeploymentActorResponse(BaseModel):
    id: UUID
    display_name: str


class DeploymentResponse(BaseModel):
    id: UUID
    project_id: UUID
    prompt_id: UUID
    prompt_key: str
    version_id: UUID
    version_number: int
    environment: DeploymentEnvironment
    status: DeploymentStatus
    request_note: str | None
    review_note: str | None
    rollback_reason: str | None
    rollback_of_id: UUID | None
    requested_by: DeploymentActorResponse
    reviewed_by: DeploymentActorResponse | None
    requested_at: datetime
    reviewed_at: datetime | None
    activated_at: datetime | None
    validation_id: UUID | None = None


class DeploymentTimelineEvent(BaseModel):
    id: UUID
    version_id: UUID
    version_number: int
    status: DeploymentStatus
    requested_at: datetime
    reviewed_at: datetime | None
    activated_at: datetime | None


class DeploymentDetailResponse(DeploymentResponse):
    timeline: list[DeploymentTimelineEvent]
    validation: ReleaseValidationResponse | None = None


class DeploymentReviewDetailResponse(BaseModel):
    deployment: DeploymentResponse
    requested_version: PromptVersionResponse
    active_version: PromptVersionResponse | None
    recent_runs: list[RunResponse]
    validation: ReleaseValidationResponse | None = None

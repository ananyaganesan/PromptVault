"""Project and membership API models."""

import re
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from api.app.schemas.users import UserRole
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
ProjectKey = Annotated[str, Field(min_length=1, max_length=63, pattern=_KEY_PATTERN.pattern)]
ProjectName = Annotated[str, Field(min_length=1, max_length=160)]


class ProjectOwnerResponse(BaseModel):
    id: UUID
    display_name: str


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    key: str
    description: str | None
    owner: ProjectOwnerResponse
    member_count: int
    prompt_count: int
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    key: ProjectKey
    description: Annotated[str | None, Field(max_length=4000)] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
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


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
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


class ProjectMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ProjectMemberResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    is_owner: bool


class ProjectInvitationResponse(BaseModel):
    id: UUID
    project_id: UUID
    email: str
    display_name: str
    created_at: datetime
    expires_at: datetime


class ProjectInvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: Annotated[str, Field(min_length=40, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]

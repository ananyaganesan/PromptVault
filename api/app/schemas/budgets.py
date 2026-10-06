"""Budget data shared by run enforcement and administration."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None = None
    project_id: UUID | None = None
    monthly_limit: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
    timezone: Annotated[str, Field(min_length=1, max_length=64)] = "UTC"

    @model_validator(mode="after")
    def require_one_target(self) -> Self:
        if (self.user_id is None) == (self.project_id is None):
            raise ValueError("exactly one of user_id or project_id is required")
        return self

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_limit: Annotated[
        Decimal | None, Field(default=None, ge=0, max_digits=18, decimal_places=6)
    ] = None
    timezone: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None

    @model_validator(mode="after")
    def require_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("updated values cannot be null")
        return self

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class BudgetResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    project_id: UUID | None
    monthly_limit: Decimal
    timezone: str
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

"""Super Admin governance API models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from api.app.providers.policy import ConfiguredProvider, ExternalProvider
from api.app.schemas.users import UserRole
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    project_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("updated values cannot be null")
        return self


class ModelSpendResponse(BaseModel):
    provider: str
    model: str
    run_count: int
    cost: Decimal


class AdminCostTrendPoint(BaseModel):
    date: date
    cost: Decimal
    run_count: int


class TopSpenderResponse(BaseModel):
    user_id: UUID
    display_name: str
    cost: Decimal


class AdminDashboardResponse(BaseModel):
    month: str
    timezone: str
    user_count: int
    active_user_count: int
    project_count: int
    prompt_count: int
    run_count: int
    completed_run_count: int
    failed_run_count: int
    blocked_run_count: int
    total_spend: Decimal
    pending_approval_count: int
    spend_by_model: list[ModelSpendResponse]
    cost_trend: list[AdminCostTrendPoint]
    top_spenders: list[TopSpenderResponse]
    refreshed_through: datetime


class ProviderKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ExternalProvider
    alias: Annotated[str, Field(min_length=1, max_length=120)]
    secret: Annotated[str, Field(min_length=1, max_length=10_000, repr=False)]

    @field_validator("provider", "alias")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("secret")
    @classmethod
    def reject_blank_secret(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ProviderKeyResponse(BaseModel):
    id: UUID
    provider: str
    alias: str
    created_by: UUID
    created_at: datetime
    deactivated_at: datetime | None


class ModelPricingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ConfiguredProvider
    model: Annotated[str, Field(min_length=1, max_length=160)]
    input_price_per_million: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
    output_price_per_million: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
    effective_from: datetime
    effective_to: datetime | None = None

    @field_validator("provider", "model")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.effective_from.tzinfo is None:
            raise ValueError("effective_from must include a timezone")
        if self.effective_to is not None:
            if self.effective_to.tzinfo is None:
                raise ValueError("effective_to must include a timezone")
            if self.effective_to <= self.effective_from:
                raise ValueError("effective_to must be after effective_from")
        return self


class ModelPricingResponse(ModelPricingCreate):
    id: UUID
    created_by: UUID | None
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: int
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_data: dict[str, object] | None
    after_data: dict[str, object] | None
    request_id: str | None
    created_at: datetime


class MaterializedViewStatus(BaseModel):
    name: str
    is_populated: bool
    refreshed_through: datetime | None


class RunPartitionStatus(BaseModel):
    name: str
    range_expression: str


class MaintenanceJobStatus(BaseModel):
    name: str
    status: Literal["never_run", "completed"]
    last_completed_at: datetime | None


class MaintenanceStatusResponse(BaseModel):
    database: str
    materialized_views: list[MaterializedViewStatus]
    run_partitions: list[RunPartitionStatus]
    maintenance_jobs: list[MaintenanceJobStatus]
    active_provider_key_count: int
    pending_deployment_count: int
    checked_at: datetime


class ViewRefreshResponse(BaseModel):
    status: str
    views: list[str]
    completed_at: datetime


class PartitionCreateResponse(BaseModel):
    partition_name: str
    already_existed: bool

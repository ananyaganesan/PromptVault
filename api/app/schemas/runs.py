"""Run execution, ledger, and personal dashboard API models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunStatus = Literal["completed", "failed", "blocked"]


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID
    variables: dict[str, Annotated[str, Field(max_length=100_000)]] = Field(
        default_factory=dict,
        max_length=100,
    )

    @model_validator(mode="after")
    def limit_total_variable_size(self) -> "RunCreate":
        if sum(len(key) + len(value) for key, value in self.variables.items()) > 100_000:
            raise ValueError("combined variable content must not exceed 100000 characters")
        return self


class RunResponse(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    prompt_id: UUID
    prompt_key: str
    version_id: UUID
    version_number: int
    status: RunStatus
    provider: str
    model: str
    input_variables: dict[str, str]
    output_text: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost: Decimal
    error_code: str | None
    created_at: datetime


class CostTrendPoint(BaseModel):
    date: date
    cost: Decimal
    run_count: int


class PersonalDashboardResponse(BaseModel):
    month: str
    timezone: str
    project_count: int
    prompt_count: int
    run_count: int
    completed_run_count: int
    failed_run_count: int
    blocked_run_count: int
    monthly_spend: Decimal
    monthly_budget: Decimal | None
    pending_approval_count: int
    cost_trend: list[CostTrendPoint]
    recent_runs: list[RunResponse]
    refreshed_through: datetime

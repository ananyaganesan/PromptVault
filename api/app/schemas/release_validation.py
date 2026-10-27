"""Release checks embedded in deployment creation and approval."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from api.app.schemas.evaluations import (
    DEFAULT_WEIGHTS,
    CheckResult,
    EvaluationCase,
    EvaluationResponse,
    EvaluationSetup,
    Metric,
    Requirements,
    StrictModel,
)
from pydantic import BaseModel, Field


class ReleaseTestSuite(StrictModel):
    goal: Annotated[str, Field(min_length=10, max_length=2000)]
    cases: list[EvaluationCase] = Field(min_length=1, max_length=5)
    requirements: Requirements = Field(default_factory=Requirements)
    weights: dict[Metric, int] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


class ReleaseValidationCreate(StrictModel):
    id: UUID
    version_id: UUID
    environment: Literal["dev", "staging", "prod"]
    suite: ReleaseTestSuite | None = None


class ReleaseValidationLink(StrictModel):
    validation_id: UUID


class ReleaseValidationResponse(BaseModel):
    id: UUID
    version_id: UUID
    environment: Literal["dev", "staging", "prod"]
    created_by: UUID
    base_deployment_id: UUID | None
    created_at: datetime
    status: Literal["queued", "running", "passed", "blocked", "stale"]
    summary: str
    checks: list[CheckResult]
    configuration: EvaluationSetup | None
    evaluation: EvaluationResponse | None
    minimum_score: int = 70

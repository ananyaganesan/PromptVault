"""Bounded, reviewable evaluation inputs and strict Gemini judge responses."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Metric = Literal["correctness", "relevance", "instruction_following", "completeness", "clarity"]
Preset = Literal["accurate_answers", "customer_support", "summarization", "structured_json"]
METRIC_DEFINITIONS: dict[Metric, str] = {
    "correctness": "Agreement with the supplied reference, without unsupported factual claims.",
    "relevance": "Directly addresses the question and the desired outcome.",
    "instruction_following": (
        "Follows the requested format, tone, constraints, and task instructions."
    ),
    "completeness": "Includes the essential information and next steps required by the goal.",
    "clarity": "Easy to understand, well organized, and appropriately concise.",
}
DEFAULT_WEIGHTS: dict[Metric, int] = {
    "correctness": 30,
    "relevance": 25,
    "instruction_following": 20,
    "completeness": 15,
    "clarity": 10,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvaluationCase(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    variables: dict[
        str, Annotated[str, StringConstraints(strip_whitespace=False), Field(max_length=2000)]
    ] = Field(default_factory=dict, max_length=30)
    reference: Annotated[str, Field(max_length=3000)] = ""

    @model_validator(mode="after")
    def bounded_input(self) -> Self:
        if sum(len(k) + len(v) for k, v in self.variables.items()) > 4000:
            raise ValueError("Test case inputs must fit within 4000 characters")
        return self


class Requirements(StrictModel):
    valid_json: bool = False
    required_fields: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    max_words: Annotated[int, Field(ge=1, le=10000)] | None = None

    @model_validator(mode="after")
    def fields_require_json(self) -> Self:
        if self.required_fields and not self.valid_json:
            raise ValueError("Required fields need the valid JSON requirement")
        if len(set(self.required_fields)) != len(self.required_fields):
            raise ValueError("Required field names must be unique")
        return self


class EvaluationSetup(StrictModel):
    version_ids: list[UUID] = Field(min_length=1, max_length=5)
    goal: Annotated[str, Field(min_length=10, max_length=2000)]
    preset: Preset = "accurate_answers"
    use_embeddings: bool = False
    cases: list[EvaluationCase] = Field(min_length=1, max_length=5)
    weights: dict[Metric, Annotated[int, Field(strict=True, ge=0, le=100)]] = Field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )
    requirements: Requirements = Field(default_factory=Requirements)

    @model_validator(mode="after")
    def valid_comparison(self) -> Self:
        if len(set(self.version_ids)) != len(self.version_ids):
            raise ValueError("Select distinct versions")
        if len(self.version_ids) * len(self.cases) > 15:
            raise ValueError("Compare at most 15 version/test-case combinations")
        if len({case.name.casefold() for case in self.cases}) != len(self.cases):
            raise ValueError("Test case names must be unique")
        if set(self.weights) != set(DEFAULT_WEIGHTS) or sum(self.weights.values()) != 100:
            raise ValueError("Include all five metric weights, totaling 100")
        if not any(self.weights[key] for key in self.weights if key != "correctness") and not all(
            case.reference for case in self.cases
        ):
            raise ValueError("Correctness-only evaluation needs a reference for every case")
        return self


class ComparisonSetup(EvaluationSetup):
    # Historical evaluations retain their original flag; new comparisons always embed.
    use_embeddings: Literal[True] = True

    @model_validator(mode="before")
    @classmethod
    def enable_embeddings(cls, data: object) -> object:
        if isinstance(data, dict):
            return {**data, "use_embeddings": True}
        return data

    version_ids: list[UUID] = Field(min_length=2, max_length=5)


class EvaluationCreate(StrictModel):
    id: UUID
    configuration: ComparisonSetup

    @model_validator(mode="after")
    def comparison_needs_two_versions(self) -> Self:
        if len(self.configuration.version_ids) < 2:
            raise ValueError("Compare at least two versions")
        return self


class SuggestionRequest(StrictModel):
    version_ids: list[UUID] = Field(min_length=2, max_length=5)
    goal: Annotated[str, Field(min_length=10, max_length=2000)]
    preset: Preset = "accurate_answers"


class SuggestedSetup(StrictModel):
    cases: list[EvaluationCase] = Field(min_length=1, max_length=3)
    weights: dict[Metric, Annotated[int, Field(strict=True, ge=0, le=100)]]
    requirements: Requirements
    notes: Annotated[str, Field(min_length=1, max_length=1000)]


class MetricScore(StrictModel):
    score: Annotated[float, Field(strict=True, ge=0, le=5, allow_inf_nan=False)]
    reason: Annotated[str, Field(min_length=1, max_length=600)]
    evidence: Annotated[str, Field(max_length=240)] = ""


class JudgeResponse(StrictModel):
    scores: dict[Metric, MetricScore]
    summary: Annotated[str, Field(min_length=1, max_length=1000)]


class CheckResult(StrictModel):
    name: str
    passed: bool
    detail: str


class EmbeddingComparison(StrictModel):
    model: str
    similarity_weight: Annotated[float, Field(ge=0, le=1)] = 0.3
    output_vector: list[float]
    reference_vector: list[float]
    cosine_similarity: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
    quality_score: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class CaseResult(StrictModel):
    version_id: UUID
    case_index: int
    run_id: UUID | None = None
    output: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    checks: list[CheckResult] = Field(default_factory=list)
    scores: dict[Metric, MetricScore] = Field(default_factory=dict)
    weighted_score: float | None = None
    embedding: EmbeddingComparison | None = None
    summary: str = ""
    error: str | None = None


class VersionRanking(StrictModel):
    version_id: UUID
    score: float | None
    eligible: bool
    passed_cases: int
    total_cases: int
    reason: str


class EvaluationResponse(BaseModel):
    id: UUID
    prompt_id: UUID
    created_by: UUID
    configuration: EvaluationSetup
    version_snapshots: list[dict[str, object]]
    status: Literal["queued", "running", "completed", "failed", "interrupted"]
    results: list[CaseResult]
    ranking: list[VersionRanking]
    recommendation: str
    winner_version_id: UUID | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    usage: dict[str, int] = Field(default_factory=dict)


class ImprovementRequest(StrictModel):
    version_id: UUID


class ImprovementDraft(StrictModel):
    template: Annotated[str, Field(min_length=1, max_length=10000)]
    explanation: Annotated[str, Field(min_length=1, max_length=2000)]

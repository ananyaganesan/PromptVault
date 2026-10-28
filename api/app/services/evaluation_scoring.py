"""Deterministic requirements, validated evidence, and conservative ranking."""

import json
import math
from uuid import UUID

from api.app.schemas.evaluations import (
    CaseResult,
    CheckResult,
    EvaluationSetup,
    JudgeResponse,
    Requirements,
    VersionRanking,
)


def parse_json_object(text: str) -> object:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Duplicate JSON fields and non-finite constants are ambiguous and rejected.
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError("Invalid JSON constant")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def check_requirements(output: str, requirements: Requirements) -> list[CheckResult]:
    checks = []
    if requirements.max_words is not None:
        count = len(output.split())
        checks.append(
            CheckResult(
                name="Word limit",
                passed=count <= requirements.max_words,
                detail=f"{count} words; limit {requirements.max_words}",
            )
        )
    if requirements.valid_json:
        try:
            parsed = parse_json_object(output)
            # Markdown fences are acceptable for judging responses, not strict JSON output.
            valid = not output.strip().startswith("```")
        except (ValueError, IndexError):
            parsed, valid = None, False
        checks.append(
            CheckResult(
                name="Valid JSON",
                passed=valid,
                detail="Output must be JSON without Markdown fences.",
            )
        )
        for field in requirements.required_fields:
            present = valid and isinstance(parsed, dict) and field in parsed
            checks.append(
                CheckResult(
                    name=f"Field: {field}", passed=present, detail="Required top-level JSON field."
                )
            )
    return checks


def validate_judgment(
    raw: str, setup: EvaluationSetup, output: str, reference: str
) -> JudgeResponse:
    judgment = JudgeResponse.model_validate(parse_json_object(raw))
    expected = {
        key
        for key, weight in setup.weights.items()
        if weight > 0 and (key != "correctness" or reference)
    }
    if set(judgment.scores) != expected:
        raise ValueError("Judge did not score the requested metrics")
    for score in judgment.scores.values():
        if not score.evidence or score.evidence not in output:
            raise ValueError("Judge evidence must quote the actual output")
    return judgment


def score_result(result: CaseResult, setup: EvaluationSetup) -> float:
    total = sum(setup.weights[key] for key in result.scores)
    if not total:
        raise ValueError("No assessable metrics")
    return round(
        sum(score.score * setup.weights[key] for key, score in result.scores.items()) / total * 20,
        2,
    )


def rank_versions(
    setup: EvaluationSetup, results: list[CaseResult]
) -> tuple[list[VersionRanking], UUID | None, str]:
    rankings = []
    incomplete = len(results) != len(setup.version_ids) * len(setup.cases)
    for version in setup.version_ids:
        rows = [row for row in results if row.version_id == version]
        complete = len(rows) == len(setup.cases) and all(
            row.weighted_score is not None and row.error is None for row in rows
        )
        incomplete = incomplete or not complete
        passed = sum(not row.error and all(check.passed for check in row.checks) for row in rows)
        eligible = complete and passed == len(setup.cases)
        mean = (
            round(sum(row.weighted_score or 0 for row in rows) / len(rows), 2) if complete else None
        )
        rankings.append(
            VersionRanking(
                version_id=version,
                score=mean,
                eligible=eligible,
                passed_cases=passed,
                total_cases=len(setup.cases),
                reason="Meets every mandatory check."
                if eligible
                else "Incomplete evaluation."
                if not complete
                else "Failed a mandatory check.",
            )
        )
    rankings.sort(key=lambda item: (not item.eligible, -(item.score or 0)))
    if incomplete:
        return rankings, None, "No recommendation: some outputs could not be fully evaluated."
    eligible_rows = [row for row in rankings if row.eligible]
    if not eligible_rows:
        return rankings, None, "No version met every mandatory requirement."
    if len(eligible_rows) > 1 and (eligible_rows[0].score or 0) - (eligible_rows[1].score or 0) < 3:
        return (
            rankings,
            None,
            "No clear winner: leading scores are within 3 points. Try more cases.",
        )
    return (
        rankings,
        eligible_rows[0].version_id,
        (
            "Recommended for these test cases: highest quality score among versions meeting all "
            "requirements."
        ),
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compare finite, equal-sized nonzero vectors without assuming normalization."""
    if not left or len(left) != len(right):
        raise ValueError("Embedding dimensions must match")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in [*left, *right]):
        raise ValueError("Embeddings must be finite numbers")
    left_norm, right_norm = math.hypot(*left), math.hypot(*right)
    if not left_norm or not right_norm or not math.isfinite(left_norm + right_norm):
        raise ValueError("Embedding norms must be finite and nonzero")
    value = math.fsum((a / left_norm) * (b / right_norm) for a, b in zip(left, right, strict=True))
    return max(-1.0, min(1.0, value))


def blend_embedding_score(quality_score: float, similarity: float) -> float:
    # Negative similarity contributes zero; it never becomes positive agreement.
    return round(0.8 * quality_score + 0.2 * max(0.0, similarity) * 100, 2)

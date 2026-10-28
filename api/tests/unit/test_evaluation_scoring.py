"""Mandatory requirements, trustworthy scoring, and incomplete-comparison safeguards."""

import json
from uuid import uuid4

import pytest
from api.app.schemas.evaluations import (
    CaseResult,
    EvaluationSetup,
    MetricScore,
    Requirements,
)
from api.app.services.evaluation_scoring import (
    blend_embedding_score,
    check_requirements,
    cosine_similarity,
    parse_json_object,
    rank_versions,
    score_result,
    validate_judgment,
)
from pydantic import ValidationError


def setup(**changes):
    return EvaluationSetup.model_validate(
        {
            "version_ids": [str(uuid4()), str(uuid4())],
            "goal": "Answer clearly and accurately.",
            "cases": [{"name": "Typical", "variables": {"question": "Why?"}}],
            **changes,
        }
    )


def result(config, index, score, **changes):
    return CaseResult(
        version_id=config.version_ids[index],
        case_index=0,
        scores={"clarity": MetricScore(score=float(score), reason="Readable.", evidence="Answer")},
        weighted_score=score * 20,
        **changes,
    )


@pytest.mark.parametrize(
    "output,valid",
    [
        ('{"answer":"yes"}', True),
        ('```json\n{"answer":"yes"}\n```', False),
        ('{"answer":1,"answer":2}', False),
        ('{"answer":NaN}', False),
        ("no", False),
    ],
)
def test_mandatory_json_is_strict(output, valid):
    checks = check_requirements(output, Requirements(valid_json=True, required_fields=["answer"]))
    assert checks[0].passed is valid
    assert checks[1].passed is valid


def test_json_fields_need_an_object_and_word_limit_is_independent():
    checks = check_requirements(
        "[1,2,3]", Requirements(valid_json=True, required_fields=["answer"], max_words=1)
    )
    assert [check.passed for check in checks] == [True, True, False]
    assert not check_requirements("one two three", Requirements(max_words=2))[0].passed


def test_no_reference_removes_correctness_and_renormalizes_weights():
    config = setup()
    output = "A concise answer."
    raw = json.dumps(
        {
            "scores": {
                metric: {"score": 4, "reason": "Meets the goal.", "evidence": "concise"}
                for metric in config.weights
                if metric != "correctness"
            },
            "summary": "Good.",
        }
    )
    judged = validate_judgment(raw, config, output, "")
    row = CaseResult(version_id=config.version_ids[0], case_index=0, scores=judged.scores)
    assert "correctness" not in judged.scores
    assert score_result(row, config) == 80
    with pytest.raises(ValueError):
        validate_judgment(raw, config, output, "Trusted reference")


@pytest.mark.parametrize(
    "change",
    [
        {"score": 6},
        {"score": True},
        {"score": "5"},
        {"evidence": "fabricated quote"},
        {"evidence": ""},
    ],
)
def test_invalid_or_fabricated_judgments_are_rejected(change):
    config = setup(
        weights={
            "correctness": 0,
            "relevance": 0,
            "instruction_following": 0,
            "completeness": 0,
            "clarity": 100,
        }
    )
    raw = json.dumps(
        {
            "scores": {"clarity": {"score": 4, "reason": "Clear.", "evidence": "Answer", **change}},
            "summary": "Clear.",
        }
    )
    with pytest.raises((ValueError, ValidationError)):
        validate_judgment(raw, config, "Answer", "")


def test_hard_failure_disqualifies_the_higher_scoring_version():
    config = setup()
    high = result(
        config, 0, 5, checks=check_requirements("not JSON", Requirements(valid_json=True))
    )
    low = result(config, 1, 4, checks=check_requirements("{}", Requirements(valid_json=True)))
    ranking, winner, _ = rank_versions(config, [high, low])
    assert winner == config.version_ids[1]
    assert ranking[0].eligible and not ranking[1].eligible


def test_missing_assessment_prevents_any_recommendation():
    config = setup()
    for rows in (
        [result(config, 0, 5)],
        [
            result(config, 0, 5),
            CaseResult(version_id=config.version_ids[1], case_index=0, error="timeout"),
        ],
    ):
        _, winner, explanation = rank_versions(config, rows)
        assert winner is None and "fully evaluated" in explanation


def test_close_scores_do_not_force_a_winner():
    config = setup()
    _, winner, explanation = rank_versions(config, [result(config, 0, 4.5), result(config, 1, 4.4)])
    assert winner is None and "No clear winner" in explanation


@pytest.mark.parametrize(
    "changes",
    [
        {"weights": {"clarity": 100}},
        {"version_ids": ["11111111-1111-4111-8111-111111111111"] * 2},
        {"cases": [{"name": "One"}, {"name": "one"}]},
        {
            "weights": {
                "correctness": 100,
                "relevance": 0,
                "instruction_following": 0,
                "completeness": 0,
                "clarity": 0,
            }
        },
    ],
)
def test_invalid_comparison_setups_are_rejected(changes):
    with pytest.raises(ValidationError):
        setup(**changes)


def test_ambiguous_judge_json_is_rejected():
    with pytest.raises(ValueError):
        parse_json_object('{"scores":{},"scores":{}}')


def test_scenario_values_are_preserved_exactly():
    config = setup(
        cases=[
            {"name": "Whitespace", "variables": {"question": "  exact input\n"}, "reference": ""}
        ]
    )
    assert config.cases[0].variables["question"] == "  exact input\n"


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ([1, 2], [2, 4], 1),
        ([1, 0], [0, 1], 0),
        ([1, 0], [-1, 0], -1),
    ],
)
def test_cosine_similarity(left, right, expected):
    assert cosine_similarity(left, right) == pytest.approx(expected)


@pytest.mark.parametrize(
    "left,right",
    [
        ([], []),
        ([0, 0], [1, 0]),
        ([1], [1, 2]),
        ([float("nan")], [1]),
        ([float("inf")], [1]),
        ([True], [1]),
    ],
)
def test_invalid_embeddings_are_rejected(left, right):
    with pytest.raises(ValueError):
        cosine_similarity(left, right)


def test_embedding_score_affects_ranking_and_negative_similarity_is_not_agreement():
    config = setup()
    first, second = result(config, 0, 4), result(config, 1, 4)
    first.weighted_score = blend_embedding_score(80, 0.2)
    second.weighted_score = blend_embedding_score(80, 0.9)
    assert first.weighted_score == 68
    assert second.weighted_score == 82
    assert rank_versions(config, [first, second])[1] == config.version_ids[1]
    assert blend_embedding_score(80, -1) == 64


def test_historical_setups_do_not_enable_embeddings():
    assert setup().use_embeddings is False

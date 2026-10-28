"""Evaluation API with real isolated PostgreSQL and Gemini doubles under tests only."""

import asyncio
import json
from concurrent.futures import CancelledError as FutureCancelledError
from contextlib import suppress
from uuid import uuid4

import psycopg
import pytest
from api.app.main import create_app
from api.app.providers.base import ProviderResult
from api.app.providers.errors import ProviderQuotaError, ProviderTimeoutError
from api.app.schemas.evaluations import DEFAULT_WEIGHTS
from fastapi.testclient import TestClient
from tests.auth_support import create_verified_test_user, seed_owned_project
from tests.provider_support import seed_gemini_test_credential


class EvaluationGemini:
    def __init__(self):
        self.calls = []
        self.invalid_judge = False
        self.quota = False
        self.timeout = False
        self.cancel = False
        self.on_judge = None

    async def execute(self, request):
        self.calls.append(request)
        data = json.loads(request.prompt.split("\nDATA:\n")[1])
        if request.prompt.startswith("EVALUATION_JUDGE"):
            if self.cancel:
                raise asyncio.CancelledError
            if self.timeout:
                raise ProviderTimeoutError("private timeout detail")
            if self.quota:
                raise ProviderQuotaError("private upstream detail")
            if self.on_judge:
                self.on_judge()
            score = 4.8 if "STRONG" in data["candidate_output"] else 3.0
            payload = {
                "scores": {
                    key: {
                        "score": score,
                        "reason": "Follows the requested goal.",
                        "evidence": "invented evidence"
                        if self.invalid_judge
                        else data["candidate_output"][:80],
                    }
                    for key in data["metrics"]
                },
                "summary": "Useful answer with clear next steps.",
            }
        elif request.prompt.startswith("EVALUATION_SUGGEST"):
            payload = {
                "cases": [
                    {
                        "name": "Typical",
                        "variables": {key: "Example question" for key in data["variables"]},
                        "reference": "Unverified AI reference",
                    }
                ],
                "weights": DEFAULT_WEIGHTS,
                "requirements": {"valid_json": False, "required_fields": [], "max_words": None},
                "notes": "Review the examples and supply trusted references.",
            }
        else:
            payload = {
                "template": (
                    "Answer {{topic}} clearly, give relevant details, and follow all requirements."
                ),
                "explanation": "Clarifies the desired structure. This draft has not been tested.",
            }
        return ProviderResult(json.dumps(payload), 50, 80, 12)


@pytest.fixture
def evaluation_context(test_settings, seeded_database_url, monkeypatch):
    settings = test_settings.model_copy(update={"database_url": seeded_database_url})
    gemini = EvaluationGemini()
    monkeypatch.setattr("api.app.services.evaluations.get_provider", lambda *args, **kwargs: gemini)
    with TestClient(create_app(settings)) as client:
        seed_gemini_test_credential(settings)
        user, headers = create_verified_test_user(client, "evaluation-owner")
        project = seed_owned_project(
            client, headers, {"name": "Evaluation tests", "key": f"eval-{uuid4().hex}"}
        )
        config = {
            "provider": "gemini",
            "model": "gemini-3.5-flash-lite",
            "temperature": 0,
            "max_output_tokens": 100,
        }
        prompt = client.post(
            f"/api/v1/projects/{project['id']}/prompts",
            headers=headers,
            json={
                "name": "Support answer",
                "key": "answer",
                "template_body": "WEAK Answer {{topic}}.",
                "model_config": config,
                "commit_message": "Initial",
            },
        )
        assert prompt.status_code == 201, prompt.text
        prompt = prompt.json()
        first = prompt["latest_version"]
        second = client.post(
            f"/api/v1/prompts/{prompt['id']}/versions",
            headers=headers,
            json={
                "parent_version_id": first["id"],
                "template_body": "STRONG Answer {{topic}} clearly with next steps.",
                "model_config": config,
                "commit_message": "Clearer instructions",
            },
        )
        assert second.status_code == 201, second.text
        setup = {
            "version_ids": [first["id"], second.json()["id"]],
            "goal": "Give a useful and clear answer with practical next steps.",
            "cases": [
                {"name": "Typical", "variables": {"topic": "A delayed delivery"}, "reference": ""}
            ],
            "weights": DEFAULT_WEIGHTS,
            "preset": "customer_support",
            "requirements": {"valid_json": False, "required_fields": [], "max_words": 100},
        }
        yield client, headers, prompt["id"], setup, gemini, user


def start(context):
    client, headers, prompt_id, setup, _, _ = context
    payload = {"id": str(uuid4()), "configuration": setup}
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers, json=payload
    )
    assert response.status_code == 202, response.text
    result = client.get(f"/api/v1/prompts/{prompt_id}/evaluations/{payload['id']}", headers=headers)
    assert result.status_code == 200, result.text
    return payload, result.json()


@pytest.mark.database
def test_complete_comparison_history_usage_and_explicit_improvement(
    evaluation_context, seeded_database_url
):
    client, headers, prompt_id, setup, gemini, _ = evaluation_context
    payload, result = start(evaluation_context)
    assert result["status"] == "completed", result
    assert result["winner_version_id"] == setup["version_ids"][1]
    assert len(result["results"]) == 2 and all(row["run_id"] for row in result["results"])
    assert all("correctness" not in row["scores"] for row in result["results"])
    assert result["usage"]["evaluator_calls"] == 2
    assert result["usage"]["evaluator_prompt_tokens"] == 100
    assert result["version_snapshots"][0]["template_body"].startswith("WEAK")
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/evaluation-setup", headers=headers).json()[
            "configuration"
        ]["goal"]
        == setup["goal"]
    )
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers).json()[0]["id"]
        == result["id"]
    )
    assert (
        client.post(
            f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers, json=payload
        ).status_code
        == 202
    )
    assert len(gemini.calls) == 2  # Retries never repeat model calls.
    conflicting = payload | {"configuration": setup | {"goal": "A different goal for the same ID."}}
    assert (
        client.post(
            f"/api/v1/prompts/{prompt_id}/evaluations", headers=headers, json=conflicting
        ).status_code
        == 409
    )
    suggestion = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluation-suggestions",
        headers=headers,
        json={key: setup[key] for key in ("version_ids", "goal", "preset")},
    )
    assert suggestion.status_code == 200, suggestion.text
    assert suggestion.json()["cases"][0]["reference"] == ""
    before = client.get(f"/api/v1/prompts/{prompt_id}/versions", headers=headers).json()["total"]
    improved = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations/{result['id']}/improvement",
        headers=headers,
        json={"version_id": setup["version_ids"][1]},
    )
    assert improved.status_code == 200, improved.text
    assert "{{topic}}" in improved.json()["template"]
    assert (
        client.get(f"/api/v1/prompts/{prompt_id}/versions", headers=headers).json()["total"]
        == before
    )
    saved = client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "parent_version_id": setup["version_ids"][1],
            "template_body": improved.json()["template"],
            "model_config": result["version_snapshots"][1]["model_config"],
            "commit_message": "Reviewed evaluation draft",
        },
    )
    assert saved.status_code == 201
    with psycopg.connect(seeded_database_url) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM evaluation_calls "
                "WHERE evaluation_id=%s AND status='completed'",
                (result["id"],),
            ).fetchone()[0]
            == 3
        )
        assert (
            db.execute(
                "SELECT count(*) FROM deployment_context WHERE prompt_id=%s", (prompt_id,)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.database
def test_invalid_judge_or_failed_requirement_never_produces_a_winner(evaluation_context):
    evaluation_context[4].invalid_judge = True
    _, result = start(evaluation_context)
    assert result["status"] == "completed"
    assert result["winner_version_id"] is None
    assert all(row["error"] and row["weighted_score"] is None for row in result["results"])
    evaluation_context[4].invalid_judge = False
    evaluation_context[3]["requirements"]["valid_json"] = True
    _, result = start(evaluation_context)
    assert result["winner_version_id"] is None
    assert all(not row["eligible"] for row in result["ranking"])


@pytest.mark.database
def test_quota_failure_is_saved_without_retry_or_paid_fallback(evaluation_context):
    evaluation_context[4].quota = True
    _, result = start(evaluation_context)
    assert result["status"] == "failed" and result["winner_version_id"] is None
    assert "quota" in result["error"] and "private upstream detail" not in json.dumps(result)
    assert len(evaluation_context[4].calls) == 1
    assert len(result["results"]) == 1 and result["results"][0]["output"]


@pytest.mark.database
def test_access_and_version_input_boundaries(evaluation_context):
    client, headers, prompt_id, setup, gemini, _ = evaluation_context
    _, outsider = create_verified_test_user(client, "evaluation-outsider")
    base = f"/api/v1/prompts/{prompt_id}"
    for endpoint in ("/evaluation-setup", "/evaluations"):
        assert client.get(base + endpoint, headers=outsider).status_code == 404
    assert (
        client.post(
            base + "/evaluation-suggestions",
            headers=outsider,
            json={key: setup[key] for key in ("version_ids", "goal", "preset")},
        ).status_code
        == 404
    )
    assert (
        client.post(
            base + "/evaluations",
            headers=outsider,
            json={"id": str(uuid4()), "configuration": setup},
        ).status_code
        == 404
    )
    bad = setup | {"cases": [{"name": "Missing input", "variables": {}}]}
    assert (
        client.post(
            base + "/evaluations", headers=headers, json={"id": str(uuid4()), "configuration": bad}
        ).status_code
        == 422
    )
    bad = setup | {"version_ids": [setup["version_ids"][0], str(uuid4())]}
    assert (
        client.post(
            base + "/evaluations", headers=headers, json={"id": str(uuid4()), "configuration": bad}
        ).status_code
        == 404
    )
    assert not gemini.calls


@pytest.mark.database
def test_membership_removed_during_judging_stops_further_calls(
    evaluation_context, seeded_database_url
):
    client, _, prompt_id, setup, gemini, owner = evaluation_context
    user, headers = create_verified_test_user(client, "evaluation-member")
    with psycopg.connect(seeded_database_url) as db:
        db.execute(
            "INSERT INTO project_members(project_id,user_id,added_by) "
            "SELECT project_id,%s,%s FROM prompts WHERE id=%s",
            (user["id"], owner["id"], prompt_id),
        )

    def remove_membership():
        with psycopg.connect(seeded_database_url) as db:
            db.execute("DELETE FROM project_members WHERE user_id=%s", (user["id"],))

    gemini.on_judge = remove_membership
    evaluation_id = str(uuid4())
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations",
        headers=headers,
        json={"id": evaluation_id, "configuration": setup},
    )
    assert response.status_code == 202
    assert len(gemini.calls) == 1
    assert (
        client.get(
            f"/api/v1/prompts/{prompt_id}/evaluations/{evaluation_id}", headers=headers
        ).status_code
        == 404
    )
    with psycopg.connect(seeded_database_url) as db:
        assert db.execute(
            "SELECT status,winner_version_id FROM prompt_evaluations WHERE id=%s", (evaluation_id,)
        ).fetchone() == ("failed", None)
        assert db.execute(
            "SELECT status FROM evaluation_calls WHERE evaluation_id=%s", (evaluation_id,)
        ).fetchone() == ("completed",)


@pytest.mark.database
def test_evaluation_history_does_not_block_project_deletion(
    evaluation_context, seeded_database_url
):
    client, _, prompt_id, _, _, _ = evaluation_context
    _, evaluation = start(evaluation_context)
    assert evaluation["winner_version_id"]
    root = client.post(
        "/api/v1/auth/login", json={"email": "admin@promptvault.dev", "password": "AdminDemo2026!"}
    )
    assert root.status_code == 200
    with psycopg.connect(seeded_database_url) as db:
        project_id = db.execute(
            "SELECT project_id FROM prompts WHERE id=%s", (prompt_id,)
        ).fetchone()[0]
    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {root.json()['access_token']}"},
    )
    assert deleted.status_code == 204, deleted.text
    with psycopg.connect(seeded_database_url) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM prompt_evaluations WHERE id=%s", (evaluation["id"],)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.database
def test_judge_timeout_preserves_outputs_and_never_selects_a_winner(evaluation_context):
    evaluation_context[4].timeout = True
    _, result = start(evaluation_context)
    assert result["status"] == "completed" and result["winner_version_id"] is None
    assert len(result["results"]) == 2
    assert all(
        row["output"] and row["error"] and row["weighted_score"] is None
        for row in result["results"]
    )
    assert "private timeout detail" not in json.dumps(result)


@pytest.mark.database
def test_interrupted_judging_preserves_the_generated_answer(
    evaluation_context, seeded_database_url
):
    client, headers, prompt_id, setup, gemini, _ = evaluation_context
    gemini.cancel = True
    evaluation_id = str(uuid4())
    with suppress(FutureCancelledError, asyncio.CancelledError):
        client.post(
            f"/api/v1/prompts/{prompt_id}/evaluations",
            headers=headers,
            json={"id": evaluation_id, "configuration": setup},
        )
    with psycopg.connect(seeded_database_url) as db:
        row = db.execute(
            "SELECT status,results,winner_version_id FROM prompt_evaluations WHERE id=%s",
            (evaluation_id,),
        ).fetchone()
        assert row[0] == "interrupted" and row[2] is None
        assert len(row[1]) == 1 and row[1][0]["output"]
        assert db.execute(
            "SELECT status FROM evaluation_calls WHERE evaluation_id=%s", (evaluation_id,)
        ).fetchone() == ("interrupted",)


@pytest.mark.database
def test_embeddings_are_saved_blended_and_reference_is_reused(evaluation_context, monkeypatch):
    from api.app.providers.gemini import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

    texts = []

    class Embeddings:
        async def execute(self, request):
            texts.append(request.prompt)
            vector = [0.0] * EMBEDDING_DIMENSIONS
            vector[0 if "WEAK" not in request.prompt else 1] = 1.0
            return ProviderResult(json.dumps(vector), 10, 0, 2)

    monkeypatch.setattr(
        "api.app.services.evaluations.GeminiEmbeddingProvider", lambda *a, **kw: Embeddings()
    )
    setup = evaluation_context[3]
    setup["use_embeddings"] = False  # Older clients cannot disable new comparisons.
    setup["cases"][0]["reference"] = "Give clear next steps."
    _, result = start(evaluation_context)
    assert result["status"] == "completed", result
    assert result["configuration"]["use_embeddings"] is True
    assert result["winner_version_id"] == setup["version_ids"][1]
    rows = {row["version_id"]: row for row in result["results"]}
    assert rows[setup["version_ids"][0]]["embedding"]["cosine_similarity"] == 0
    strong = rows[setup["version_ids"][1]]
    assert strong["embedding"]["cosine_similarity"] == 1
    assert strong["embedding"]["model"] == EMBEDDING_MODEL
    assert strong["embedding"]["similarity_weight"] == 0.2
    assert len(strong["embedding"]["output_vector"]) == EMBEDDING_DIMENSIONS
    assert strong["weighted_score"] == 96.8
    assert texts.count("Give clear next steps.") == 1
    assert result["usage"]["evaluator_calls"] == 5


@pytest.mark.database
def test_embedding_failure_preserves_answer_without_recommendation(evaluation_context, monkeypatch):
    class Embeddings:
        async def execute(self, request):
            raise ProviderTimeoutError("private embedding timeout")

    monkeypatch.setattr(
        "api.app.services.evaluations.GeminiEmbeddingProvider", lambda *a, **kw: Embeddings()
    )
    setup = evaluation_context[3]
    setup["use_embeddings"] = True
    setup["cases"][0]["reference"] = "A trusted answer."
    _, result = start(evaluation_context)
    assert result["winner_version_id"] is None
    assert all(row["output"] and row["weighted_score"] is None for row in result["results"])
    assert "private embedding timeout" not in json.dumps(result)


@pytest.mark.database
def test_embeddings_without_reference_use_quality_only(evaluation_context, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("No reference should mean no embedding call")

    monkeypatch.setattr("api.app.services.evaluations.GeminiEmbeddingProvider", unexpected)
    evaluation_context[3]["use_embeddings"] = True
    _, result = start(evaluation_context)
    assert result["winner_version_id"]
    assert all(row["embedding"] is None for row in result["results"])
    assert result["usage"]["evaluator_calls"] == 2

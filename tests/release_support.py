"""Release evidence helpers for isolated test databases, never runtime adapters."""

import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from api.app.providers.base import ProviderResult


class ReleaseJudge:
    async def execute(self, request):
        data = json.loads(request.prompt.split("\nDATA:\n")[1])
        result = {
            "scores": {
                key: {
                    "score": 4.5,
                    "reason": "Meets the test goal.",
                    "evidence": data["candidate_output"][:80],
                }
                for key in data["metrics"]
            },
            "summary": "Meets the release test requirements.",
        }
        return ProviderResult(json.dumps(result), 30, 60, 10)


def validated_deployment(client, path="/api/v1/deployments", **kwargs):
    """Exercise the actual validation API before existing lifecycle tests request a release."""
    payload = kwargs.get("json", {})
    if (
        payload.get("environment") in ("dev", "staging", "prod")
        and payload.get("version_id")
        and not payload.get("validation_id")
        and set(payload) <= {"version_id", "environment", "request_note"}
        and not kwargs.get("params")
    ):
        headers = kwargs.get("headers", {})
        version = client.get(
            f"/api/v1/versions/{payload['version_id']}", headers=headers
        )
        if version.status_code == 200:
            validation_id = str(uuid4())
            response = client.post(
                "/api/v1/deployments/validations",
                headers=headers,
                json={
                    "id": validation_id,
                    "version_id": payload["version_id"],
                    "environment": payload["environment"],
                    "suite": {
                        "goal": "Answer the request clearly and follow the prompt instructions.",
                        "cases": [
                            {
                                "name": "Release fixture",
                                "variables": {
                                    name: "Example"
                                    for name in version.json()["variables"]
                                },
                            }
                        ],
                    },
                },
            )
            assert response.status_code == 202, response.text
            report = client.get(
                f"/api/v1/deployments/validations/{validation_id}", headers=headers
            )
            assert report.json()["status"] == "passed", report.text
            kwargs["json"] = {**payload, "validation_id": validation_id}
    return client.post(path, **kwargs)


def seed_release_evidence(connection, version_id, actor_id, environment="prod"):
    """SQL concurrency fixtures need committed evidence without running HTTP inside their transaction."""
    db_name = connection.execute("SELECT current_database()").fetchone()
    name = next(iter(db_name.values())) if isinstance(db_name, dict) else db_name[0]
    if not name.endswith("_test"):
        raise RuntimeError("Release fixtures require an isolated _test database")
    evaluation_id, validation_id = uuid4(), uuid4()
    cursor = connection.execute(
        "SELECT prompt_id FROM prompt_versions WHERE id=%s", (version_id,)
    )
    record = cursor.fetchone()
    prompt_id = record["prompt_id"] if isinstance(record, dict) else record[0]
    setup = {
        "version_ids": [str(version_id)],
        "goal": "Exercise an isolated lifecycle fixture.",
        "cases": [{"name": "Fixture", "variables": {}, "reference": ""}],
        "weights": {
            "correctness": 30,
            "relevance": 25,
            "instruction_following": 20,
            "completeness": 15,
            "clarity": 10,
        },
        "requirements": {},
    }
    connection.execute(
        """INSERT INTO prompt_evaluations(id,prompt_id,created_by,configuration,
        version_snapshots,status,results) VALUES(%s,%s,%s,%s,'[]','completed',%s)""",
        (
            evaluation_id,
            prompt_id,
            actor_id,
            Jsonb(setup),
            Jsonb(
                [
                    {
                        "version_id": str(version_id),
                        "case_index": 0,
                        "weighted_score": 90,
                        "error": None,
                        "checks": [],
                    }
                ]
            ),
        ),
    )
    connection.execute(
        """INSERT INTO release_validations(id,version_id,environment,created_by,
        base_deployment_id,setup_source,request_payload,configuration,checks,evaluation_id)
        VALUES(%s,%s,%s,%s,(SELECT id FROM deployment_context WHERE prompt_id=%s
            AND environment=%s AND status='active'),
        (SELECT configuration FROM prompt_evaluation_setups WHERE prompt_id=%s),
        '{}',%s,'[]',%s)""",
        (
            validation_id,
            version_id,
            environment,
            actor_id,
            prompt_id,
            environment,
            prompt_id,
            Jsonb(setup),
            evaluation_id,
        ),
    )
    return validation_id

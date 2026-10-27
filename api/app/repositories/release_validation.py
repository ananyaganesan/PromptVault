"""Read release evidence and derive its current validity using the database gate."""

from uuid import UUID

from api.app.db.orm import ORMConnection
from api.app.repositories.evaluations import EvaluationRepository
from api.app.schemas.evaluations import EvaluationResponse
from api.app.schemas.release_validation import ReleaseValidationResponse


async def release_report(
    connection: ORMConnection, validation_id: UUID
) -> ReleaseValidationResponse | None:
    cursor = await connection.execute(
        """SELECT *,release_validation_problem(id,version_id,environment) AS problem
        FROM release_validations WHERE id=%s""",
        (validation_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    evaluation = None
    if row["evaluation_id"]:
        evaluation = EvaluationResponse.model_validate(
            await EvaluationRepository(connection).get(row["evaluation_id"])
        )
    problem = row.pop("problem")
    state = problem.split(":", 1)[0] if problem else "passed"
    if state == "running" and evaluation and evaluation.status == "queued":
        state = "queued"
    return ReleaseValidationResponse(
        **{
            key: value
            for key, value in row.items()
            if key not in ("evaluation_id", "setup_source", "configuration", "request_payload")
        },
        configuration=row["configuration"] or None,
        status=state,  # type: ignore[arg-type]
        summary=problem.split(": ", 1)[-1] if problem else "Every release check passed.",
        evaluation=evaluation,
    )

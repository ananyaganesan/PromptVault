"""Validation lives under deployments rather than a separate user workspace."""

from uuid import UUID

from api.app.dependencies.auth import DetachedCurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.errors import error_responses
from api.app.routers.evaluations import Evaluation, session_id
from api.app.schemas.evaluations import ImprovementDraft
from api.app.schemas.release_validation import ReleaseValidationCreate, ReleaseValidationResponse
from api.app.services.release_validation import ReleaseValidationService
from fastapi import APIRouter, BackgroundTasks, Depends, Request

router = APIRouter(
    prefix="/api/v1/deployments/validations",
    tags=["deployments"],
    responses=error_responses(401, 404, 409, 422, 429, 502, 503, 504),
    dependencies=[Depends(allow_query_parameters())],
)


@router.post("", status_code=202, response_model=ReleaseValidationResponse)
async def validate_release(
    payload: ReleaseValidationCreate,
    request: Request,
    tasks: BackgroundTasks,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> ReleaseValidationResponse:
    session = session_id(request)
    report = await ReleaseValidationService(evaluator).create(payload, actor, session)
    if report.evaluation and report.evaluation.status == "queued":
        tasks.add_task(evaluator.run, report.evaluation.id, actor, session)
    return report


@router.get("/{validation_id}", response_model=ReleaseValidationResponse)
async def get_release_validation(
    validation_id: UUID, request: Request, actor: DetachedCurrentUser, evaluator: Evaluation
) -> ReleaseValidationResponse:
    return await ReleaseValidationService(evaluator).get(validation_id, actor, session_id(request))


@router.post("/{validation_id}/suggest-fix", response_model=ImprovementDraft)
async def suggest_fix(
    validation_id: UUID, request: Request, actor: DetachedCurrentUser, evaluator: Evaluation
) -> ImprovementDraft:
    return await ReleaseValidationService(evaluator).suggest_fix(
        validation_id, actor, session_id(request)
    )

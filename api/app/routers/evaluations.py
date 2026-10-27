"""Project-scoped evaluation setup, comparison history, and Gemini assistance."""

from typing import Annotated
from uuid import UUID

from api.app.db.pool import PoolProtocol, get_pool
from api.app.dependencies.auth import DetachedCurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.runs import RunExecution
from api.app.errors import error_responses
from api.app.schemas.evaluations import (
    ComparisonSetup,
    EvaluationCreate,
    EvaluationResponse,
    ImprovementDraft,
    ImprovementRequest,
    SuggestedSetup,
    SuggestionRequest,
)
from api.app.security import decode_access_token
from api.app.services.evaluations import EvaluationService
from fastapi import APIRouter, BackgroundTasks, Depends, Request

router = APIRouter(
    prefix="/api/v1/prompts/{prompt_id}",
    tags=["evaluations"],
    dependencies=[Depends(allow_query_parameters())],
    responses=error_responses(401, 404, 409, 422, 429, 502, 503, 504),
)


def service(
    request: Request, pool: Annotated[PoolProtocol, Depends(get_pool)], runner: RunExecution
) -> EvaluationService:
    return EvaluationService(pool, request.app.state.settings, runner)


Evaluation = Annotated[EvaluationService, Depends(service)]


def session_id(request: Request) -> UUID:
    # DetachedCurrentUser validates this token before endpoint code runs.
    return decode_access_token(
        request.headers["authorization"].split(" ", 1)[1], request.app.state.settings
    ).token_id


@router.get("/evaluation-setup")
async def get_setup(
    prompt_id: UUID, request: Request, actor: DetachedCurrentUser, evaluator: Evaluation
) -> dict[str, object]:
    return await evaluator.setup(prompt_id, actor, session_id(request))


@router.put("/evaluation-setup")
async def save_setup(
    prompt_id: UUID,
    payload: ComparisonSetup,
    request: Request,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> dict[str, object]:
    return await evaluator.save_setup(prompt_id, payload, actor, session_id(request))


@router.post("/evaluation-suggestions", response_model=SuggestedSetup)
async def suggest_cases(
    prompt_id: UUID,
    payload: SuggestionRequest,
    request: Request,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> SuggestedSetup:
    return await evaluator.suggest(prompt_id, payload, actor, session_id(request))


@router.post("/evaluations", status_code=202, response_model=EvaluationResponse)
async def start_evaluation(
    prompt_id: UUID,
    payload: EvaluationCreate,
    request: Request,
    tasks: BackgroundTasks,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> EvaluationResponse:
    session = session_id(request)
    evaluation = await evaluator.create(prompt_id, payload, actor, session)
    if evaluation.status == "queued":
        tasks.add_task(evaluator.run, evaluation.id, actor, session)
    return evaluation


@router.get("/evaluations")
async def history(
    prompt_id: UUID, request: Request, actor: DetachedCurrentUser, evaluator: Evaluation
) -> list[dict[str, object]]:
    return await evaluator.history(prompt_id, actor, session_id(request))


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    prompt_id: UUID,
    evaluation_id: UUID,
    request: Request,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> EvaluationResponse:
    return await evaluator.get(prompt_id, evaluation_id, actor, session_id(request))


@router.post("/evaluations/{evaluation_id}/improvement", response_model=ImprovementDraft)
async def suggest_improvement(
    prompt_id: UUID,
    evaluation_id: UUID,
    payload: ImprovementRequest,
    request: Request,
    actor: DetachedCurrentUser,
    evaluator: Evaluation,
) -> ImprovementDraft:
    return await evaluator.improve(
        prompt_id, evaluation_id, payload.version_id, actor, session_id(request)
    )

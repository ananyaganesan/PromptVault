"""Project-scoped runtime prompt retrieval."""

from typing import Annotated

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.query import allow_query_parameters
from api.app.errors import AppError, error_responses
from api.app.repositories.tokens import RuntimeTokenRecord, TokenRepository
from api.app.schemas.deployments import DeploymentEnvironment
from api.app.schemas.prompts import PromptKey
from api.app.schemas.tokens import ServePromptResponse
from api.app.services.serve import ServeService
from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

router = APIRouter(prefix="/serve/v1", tags=["serve"])
runtime_bearer = HTTPBearer(auto_error=False, scheme_name="RuntimeTokenBearer")


def get_serve_service(
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> ServeService:
    return ServeService(TokenRepository(connection))


ServeServiceDependency = Annotated[ServeService, Depends(get_serve_service)]


async def get_runtime_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(runtime_bearer)],
    service: ServeServiceDependency,
) -> RuntimeTokenRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            401,
            "unauthorized",
            "Runtime token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await service.authenticate(credentials.credentials)


RuntimeToken = Annotated[RuntimeTokenRecord, Depends(get_runtime_token)]


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    for candidate in if_none_match.split(","):
        normalized = candidate.strip()
        if normalized == "*" or normalized.removeprefix("W/") == etag:
            return True
    return False


@router.get(
    "/prompts/{key}",
    response_model=ServePromptResponse,
    responses={
        **error_responses(400, 401, 404, 422),
        200: {
            "description": "Project-scoped active prompt",
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
                "Vary": {"schema": {"type": "string"}},
            },
        },
        304: {
            "description": "Not Modified",
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
                "Vary": {"schema": {"type": "string"}},
            },
        },
    },
    dependencies=[Depends(allow_query_parameters("env"))],
)
async def serve_prompt(
    key: PromptKey,
    token: RuntimeToken,
    service: ServeServiceDependency,
    env: DeploymentEnvironment = "prod",
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    prompt, etag = await service.get_prompt(token, key, env)
    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=30",
        "Vary": "Authorization",
    }
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=prompt.model_dump(mode="json", by_alias=True), headers=headers)

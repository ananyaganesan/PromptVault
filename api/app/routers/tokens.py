"""Project-owner runtime token lifecycle endpoints."""

from typing import Annotated
from uuid import UUID

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.dependencies.request_context import get_request_id
from api.app.errors import error_responses
from api.app.repositories.tokens import TokenRepository
from api.app.schemas.common import Page
from api.app.schemas.tokens import ApiTokenCreate, ApiTokenCreatedResponse, ApiTokenResponse
from api.app.services.serve import TokenService
from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/api-tokens", tags=["runtime tokens"])


def get_token_service(
    request: Request,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> TokenService:
    return TokenService(TokenRepository(connection), get_request_id(request))


TokenServiceDependency = Annotated[TokenService, Depends(get_token_service)]


@router.get(
    "",
    response_model=Page[ApiTokenResponse],
    responses=error_responses(400, 401, 403, 422),
    dependencies=[Depends(allow_query_parameters("project_id", "page", "page_size"))],
)
async def list_api_tokens(
    current_user: CurrentUser,
    service: TokenServiceDependency,
    project_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ApiTokenResponse]:
    return await service.list(
        current_user, project_id=project_id, page=page, page_size=page_size
    )


@router.post(
    "",
    response_model=ApiTokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def create_api_token(
    payload: ApiTokenCreate,
    current_user: CurrentUser,
    service: TokenServiceDependency,
) -> ApiTokenCreatedResponse:
    return await service.create(payload, current_user)


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404, 409, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def revoke_api_token(
    token_id: UUID,
    current_user: CurrentUser,
    service: TokenServiceDependency,
) -> Response:
    await service.revoke(token_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

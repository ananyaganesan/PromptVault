"""Runtime token management and active prompt serving."""

from datetime import UTC, datetime
from uuid import UUID

from api.app.errors import AppError
from api.app.providers.policy import require_allowed_provider
from api.app.repositories.tokens import RuntimeTokenRecord, TokenRepository
from api.app.repositories.users import UserRecord
from api.app.schemas.common import Page
from api.app.schemas.tokens import (
    ApiTokenCreate,
    ApiTokenCreatedResponse,
    ApiTokenResponse,
    ServePromptResponse,
)
from api.app.security import generate_runtime_token, hash_runtime_token
from psycopg.errors import CheckViolation


class TokenService:
    def __init__(self, tokens: TokenRepository, request_id: str) -> None:
        self.tokens = tokens
        self.request_id = request_id

    async def _require_owner(self, project_id: UUID, actor: UserRecord) -> None:
        if not await self.tokens.is_owner(project_id, actor.id, actor.role == "admin"):
            raise AppError(403, "forbidden", "Project ownership is required")

    async def create(self, payload: ApiTokenCreate, actor: UserRecord) -> ApiTokenCreatedResponse:
        await self._require_owner(payload.project_id, actor)
        if payload.expires_at is not None and payload.expires_at <= datetime.now(UTC):
            raise AppError(
                422,
                "validation_error",
                "Request is invalid",
                {"body.expires_at": ["Expiration must be in the future"]},
            )
        plaintext = generate_runtime_token()
        await self.tokens.set_audit_context(actor.id, self.request_id)
        try:
            metadata = await self.tokens.create(
                project_id=payload.project_id,
                name=payload.name,
                token_prefix=plaintext[:20],
                token_hash=hash_runtime_token(plaintext),
                created_by=actor.id,
                expires_at=payload.expires_at,
            )
        except CheckViolation as exc:
            raise AppError(422, "validation_error", "Request is invalid") from exc
        return ApiTokenCreatedResponse(**metadata.model_dump(), token=plaintext)

    async def list(
        self,
        actor: UserRecord,
        *,
        project_id: UUID | None,
        page: int,
        page_size: int,
    ) -> Page[ApiTokenResponse]:
        if project_id is not None:
            await self._require_owner(project_id, actor)
        items, total = await self.tokens.list_scoped(
            actor_id=actor.id,
            is_admin=actor.role == "admin",
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def revoke(self, token_id: UUID, actor: UserRecord) -> None:
        project_id = await self.tokens.project_id_for_token(token_id)
        if project_id is None:
            raise AppError(404, "not_found", "API token was not found")
        await self._require_owner(project_id, actor)
        await self.tokens.set_audit_context(actor.id, self.request_id)
        if not await self.tokens.revoke(token_id, actor.id):
            raise AppError(409, "invalid_state", "API token is already revoked")


class ServeService:
    def __init__(self, tokens: TokenRepository) -> None:
        self.tokens = tokens

    async def authenticate(self, plaintext: str) -> RuntimeTokenRecord:
        if not plaintext.startswith("pv_live_"):
            raise AppError(
                401,
                "invalid_token",
                "Runtime token is invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        record = await self.tokens.authenticate(hash_runtime_token(plaintext))
        if record is None:
            raise AppError(
                401,
                "invalid_token",
                "Runtime token is invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return record

    async def get_prompt(
        self, token: RuntimeTokenRecord, key: str, environment: str
    ) -> tuple[ServePromptResponse, str]:
        result = await self.tokens.served_prompt(token.project_id, key, environment)
        if result is None:
            raise AppError(404, "not_found", "Active prompt was not found")
        prompt, deployment_id = result
        require_allowed_provider(prompt.model_configuration.provider)
        return prompt, f'"{deployment_id}:{prompt.version.id}"'

"""Prompt rendering rules shared by playground and run execution."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from api.app.db.pool import PoolProtocol
from api.app.errors import AppError
from api.app.providers.base import ProviderRequest, execute_with_timeout
from api.app.providers.catalog import require_free_model
from api.app.providers.errors import (
    ProviderCredentialError,
    ProviderExecutionError,
    ProviderModelError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from api.app.providers.factory import get_provider
from api.app.providers.policy import require_allowed_provider
from api.app.repositories.pricing import EffectivePrice, PricingRepository
from api.app.repositories.provider_keys import ProviderKeyRepository
from api.app.repositories.runs import ExecutionReservation, RunRepository, RunTarget
from api.app.repositories.users import UserRecord
from api.app.schemas.common import Page
from api.app.schemas.runs import RunCreate, RunResponse, RunStatus
from api.app.security import decrypt_provider_secret
from api.app.services.budget_enforcement import BudgetEnforcementService
from api.app.services.cost_calculation import calculate_cost
from psycopg import AsyncConnection
from psycopg import errors as database_errors

_VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
_MAX_PLACEHOLDERS = 1_000
_MAX_RENDERED_PROMPT_CHARACTERS = 200_000


class InvalidVariablesError(ValueError):
    def __init__(self, *, missing: list[str], extra: list[str]) -> None:
        super().__init__("prompt variables do not match the version contract")
        self.missing = missing
        self.extra = extra


class PromptRenderLimitError(ValueError):
    """A valid variable substitution would exceed provider-safe limits."""


def render_template(
    template: str,
    expected_variables: Sequence[str],
    supplied_variables: Mapping[str, str],
) -> str:
    expected = set(expected_variables)
    supplied = set(supplied_variables)
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected)
    if missing or extra:
        raise InvalidVariablesError(missing=missing, extra=extra)

    projected_length = len(template)
    for placeholder_count, match in enumerate(_VARIABLE_PATTERN.finditer(template), start=1):
        projected_length += len(supplied_variables[match.group(1)]) - len(match.group(0))
        if (
            placeholder_count > _MAX_PLACEHOLDERS
            or projected_length > _MAX_RENDERED_PROMPT_CHARACTERS
        ):
            raise PromptRenderLimitError("rendered prompt exceeds execution limits")

    return _VARIABLE_PATTERN.sub(
        lambda match: supplied_variables[match.group(1)],
        template,
    )


class RunExecutionService:
    def __init__(
        self,
        pool: PoolProtocol,
        request_id: str,
        provider_timeout_seconds: float,
        provider_encryption_key: str,
        gemini_api_base_url: str,
        max_concurrent_runs_per_user: int,
        allow_mock: bool = False,
    ) -> None:
        self.pool = pool
        self.request_id = request_id
        self.allow_mock = allow_mock
        self.provider_timeout_seconds = provider_timeout_seconds
        self.provider_encryption_key = provider_encryption_key
        self.gemini_api_base_url = gemini_api_base_url
        self.max_concurrent_runs_per_user = max_concurrent_runs_per_user

    async def execute(
        self,
        payload: RunCreate,
        actor: UserRecord,
        *,
        idempotency_key: str | None = None,
    ) -> RunResponse:
        executed_at = datetime.now(UTC)
        target, price, credential = await self._load_target_price_and_credential(
            payload.version_id, actor, executed_at
        )
        try:
            prompt = render_template(target.template_body, target.variables, payload.variables)
        except InvalidVariablesError as exc:
            field_errors: dict[str, list[str]] = {}
            if exc.missing:
                field_errors["body.variables"] = [f"Missing variables: {', '.join(exc.missing)}"]
            if exc.extra:
                field_errors.setdefault("body.variables", []).append(
                    f"Unexpected variables: {', '.join(exc.extra)}"
                )
            raise AppError(
                422,
                "invalid_variables",
                "Variables must exactly match the prompt version",
                field_errors,
            ) from exc
        except PromptRenderLimitError as exc:
            raise AppError(
                422,
                "validation_error",
                "Request is invalid",
                {"body.variables": ["Rendered prompt exceeds execution limits"]},
            ) from exc

        config = target.model_configuration
        if config.provider != "mock":
            model = require_free_model(config)
            if len(prompt) > model.max_input_characters:
                raise AppError(
                    422, "validation_error", "Rendered prompt exceeds this model's limit"
                )
        claim_token = uuid4()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "version_id": str(payload.version_id),
                    "variables": payload.variables,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        estimated_cost = calculate_cost(
            prompt_tokens=len(prompt.encode("utf-8")),
            completion_tokens=config.max_output_tokens,
            input_price_per_million=price.input_price_per_million,
            output_price_per_million=price.output_price_per_million,
        )
        try:
            reservation = await self._reserve(
                actor=actor,
                target=target,
                idempotency_key=idempotency_key
                or f"auto:{hashlib.sha256(self.request_id.encode('utf-8')).hexdigest()}",
                request_fingerprint=fingerprint,
                claim_token=claim_token,
                estimated_cost=estimated_cost,
                created_at=executed_at,
            )
        except database_errors.RaiseException as exc:
            if "idempotency_conflict" in str(exc):
                raise AppError(
                    409,
                    "idempotency_conflict",
                    "The idempotency key was already used for another request",
                ) from exc
            raise

        if reservation.status == "completed":
            if reservation.run_id is None:
                raise RuntimeError("completed reservation has no run")
            return await self._get_reserved_run(reservation.run_id, actor.id)
        if reservation.status in {"failed", "uncertain"}:
            raise AppError(
                409,
                "execution_outcome_unknown",
                "This execution was already attempted and cannot be safely repeated",
            )
        if reservation.status == "blocked":
            if reservation.claim_token == claim_token:
                await self._record(
                    actor=actor,
                    target=target,
                    status="blocked",
                    variables=payload.variables,
                    output_text=None,
                    prompt_tokens=0,
                    completion_tokens=0,
                    latency_ms=0,
                    cost=Decimal("0"),
                    error_code=reservation.error_code,
                    executed_at=executed_at,
                )
            if reservation.error_code == "concurrency_limit":
                raise AppError(429, "concurrency_limit", "Too many runs are already executing")
            raise AppError(409, "budget_exceeded", "Monthly budget was exceeded")
        if reservation.claim_token != claim_token:
            raise AppError(409, "execution_in_progress", "This execution is already in progress")

        try:
            result = await execute_with_timeout(
                get_provider(
                    config.provider,
                    credential=credential,
                    gemini_base_url=self.gemini_api_base_url,
                    allow_mock=self.allow_mock,
                ),
                ProviderRequest(
                    prompt=prompt,
                    model=config.model,
                    temperature=config.temperature,
                    max_output_tokens=config.max_output_tokens,
                ),
                timeout_seconds=self.provider_timeout_seconds,
            )
        except ProviderTimeoutError as exc:
            recorded = await self._record_failure(
                actor, target, payload.variables, "provider_timeout", executed_at
            )
            await self._finalize(
                reservation.id,
                status="uncertain" if config.provider != "mock" else "failed",
                actual_cost=None if config.provider != "mock" else Decimal("0"),
                run=recorded,
                error_code="provider_timeout",
            )
            raise AppError(504, "provider_timeout", "Provider request timed out") from exc
        except (ProviderQuotaError, ProviderCredentialError, ProviderModelError) as exc:
            if isinstance(exc, ProviderQuotaError):
                status_code = 429
                code = "provider_quota_exceeded"
                message = "Provider free-tier quota reached. Try again later."
            elif isinstance(exc, ProviderModelError):
                status_code = 409
                code = "model_not_available"
                message = (
                    "The selected model is no longer available. "
                    "Save a new version with a supported model."
                )
            else:
                status_code = 503
                code = "provider_configuration_error"
                message = (
                    "Provider credentials were rejected. "
                    "Ask an administrator to update the key."
                )
            recorded = await self._record_failure(
                actor, target, payload.variables, code, executed_at
            )
            await self._finalize(
                reservation.id,
                status="failed",
                actual_cost=Decimal("0"),
                run=recorded,
                error_code=code,
            )
            raise AppError(status_code, code, message) from exc
        except ProviderExecutionError as exc:
            recorded = await self._record_failure(
                actor, target, payload.variables, "provider_error", executed_at
            )
            await self._finalize(
                reservation.id,
                status="uncertain" if config.provider != "mock" else "failed",
                actual_cost=None if config.provider != "mock" else Decimal("0"),
                run=recorded,
                error_code="provider_error",
            )
            raise AppError(502, "provider_error", "Provider request failed") from exc
        except Exception as exc:
            recorded = await self._record_failure(
                actor, target, payload.variables, "provider_error", executed_at
            )
            await self._finalize(
                reservation.id,
                status="uncertain" if config.provider != "mock" else "failed",
                actual_cost=None if config.provider != "mock" else Decimal("0"),
                run=recorded,
                error_code="provider_error",
            )
            raise AppError(502, "provider_error", "Provider request failed") from exc

        cost = calculate_cost(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            input_price_per_million=price.input_price_per_million,
            output_price_per_million=price.output_price_per_million,
        )
        try:
            recorded = await self._record(
                actor=actor,
                target=target,
                status="completed",
                variables=payload.variables,
                output_text=result.output_text,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
                cost=cost,
                error_code=None,
                executed_at=executed_at,
            )
        except AppError:
            await self._finalize(
                reservation.id,
                status="uncertain",
                actual_cost=None,
                run=None,
                error_code="access_changed",
            )
            raise
        except Exception as exc:
            await self._finalize(
                reservation.id,
                status="uncertain",
                actual_cost=None,
                run=None,
                error_code="persistence_error",
            )
            raise AppError(
                503,
                "execution_outcome_unknown",
                "Provider execution completed but persistence could not be confirmed",
            ) from exc
        if recorded.status == "blocked":
            raise AppError(409, "budget_exceeded", "Monthly budget was exceeded")
        await self._finalize(
            reservation.id,
            status="completed",
            actual_cost=cost,
            run=recorded,
            error_code=None,
        )
        return recorded

    async def _reserve(
        self,
        *,
        actor: UserRecord,
        target: RunTarget,
        idempotency_key: str,
        request_fingerprint: str,
        claim_token: UUID,
        estimated_cost: Decimal,
        created_at: datetime,
    ) -> ExecutionReservation:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            async with connection.transaction():
                runs = RunRepository(connection)
                if not await runs.lock_execution_access(
                    target.version_id, actor.id, for_reservation=True
                ):
                    raise AppError(404, "not_found", "Prompt version was not found")
                return await runs.reserve_execution(
                    user_id=actor.id,
                    target=target,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    claim_token=claim_token,
                    estimated_cost=estimated_cost,
                    maximum_concurrent=self.max_concurrent_runs_per_user,
                    created_at=created_at,
                )

    async def _finalize(
        self,
        reservation_id: UUID,
        *,
        status: str,
        actual_cost: Decimal | None,
        run: RunResponse | None,
        error_code: str | None,
    ) -> None:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            async with connection.transaction():
                await RunRepository(connection).finalize_execution(
                    reservation_id,
                    status=status,
                    actual_cost=actual_cost,
                    run=run,
                    error_code=error_code,
                )

    async def _get_reserved_run(self, run_id: UUID, user_id: UUID) -> RunResponse:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            run = await RunRepository(connection).get(run_id, user_id, "admin")
            if run is None:
                raise RuntimeError("reserved run was not found")
            return run

    async def _load_target_price_and_credential(
        self,
        version_id: UUID,
        actor: UserRecord,
        executed_at: datetime,
    ) -> tuple[RunTarget, EffectivePrice, str | None]:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            async with connection.transaction():
                target = await RunRepository(connection).get_target_scoped(
                    version_id, actor.id, actor.role
                )
                if target is None:
                    raise AppError(404, "not_found", "Prompt version was not found")
                config = target.model_configuration
                require_allowed_provider(config.provider, allow_mock=self.allow_mock)
                price = await PricingRepository(connection).get_effective(
                    config.provider,
                    config.model,
                    executed_at,
                )
                if config.provider != "mock":
                    require_free_model(config)
                    if price is not None and (
                        price.input_price_per_million != 0 or price.output_price_per_million != 0
                    ):
                        raise AppError(
                            409, "model_not_free", "Paid model configuration is not allowed"
                        )
                    price = EffectivePrice(Decimal("0"), Decimal("0"))
                if price is None:
                    raise AppError(
                        409,
                        "pricing_not_configured",
                        "Model pricing is not configured",
                    )
                credential = None
                if config.provider != "mock":
                    encrypted = await ProviderKeyRepository(connection).newest_active_secret(
                        config.provider
                    )
                    if encrypted is None:
                        raise AppError(
                            409,
                            "provider_not_configured",
                            "Model provider is not configured",
                        )
                    try:
                        credential = decrypt_provider_secret(
                            encrypted, self.provider_encryption_key
                        )
                    except ValueError as exc:
                        raise AppError(
                            503,
                            "provider_configuration_error",
                            "Model provider is unavailable",
                        ) from exc
                return target, price, credential

    async def _record(
        self,
        *,
        actor: UserRecord,
        target: RunTarget,
        status: RunStatus,
        variables: dict[str, str],
        output_text: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        cost: Decimal,
        error_code: str | None,
        executed_at: datetime,
    ) -> RunResponse:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            async with connection.transaction():
                runs = RunRepository(connection)
                if not await runs.lock_execution_access(target.version_id, actor.id):
                    raise AppError(404, "not_found", "Prompt version was not found")
                return await BudgetEnforcementService(runs).record_run(
                    user_id=actor.id,
                    target=target,
                    status=status,
                    input_variables=variables,
                    output_text=output_text,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    cost=cost,
                    error_code=error_code,
                    request_id=self.request_id,
                    created_at=executed_at,
                )

    async def _record_failure(
        self,
        actor: UserRecord,
        target: RunTarget,
        variables: dict[str, str],
        error_code: str,
        executed_at: datetime,
    ) -> RunResponse:
        return await self._record(
            actor=actor,
            target=target,
            status="failed",
            variables=variables,
            output_text=None,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            cost=Decimal("0"),
            error_code=error_code,
            executed_at=executed_at,
        )


class RunQueryService:
    def __init__(self, runs: RunRepository) -> None:
        self.runs = runs

    async def get(self, run_id: UUID, actor: UserRecord) -> RunResponse:
        run = await self.runs.get(run_id, actor.id, actor.role)
        if run is None:
            raise AppError(404, "not_found", "Run was not found")
        return run

    async def list_runs(
        self,
        actor: UserRecord,
        *,
        project_id: UUID | None,
        prompt_id: UUID | None,
        version_id: UUID | None,
        status: RunStatus | None,
        model: str | None,
        search: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> Page[RunResponse]:
        if created_from is not None and created_to is not None and created_from >= created_to:
            raise AppError(400, "invalid_filter", "Query filter is invalid")
        items, total = await self.runs.list_scoped(
            user_id=actor.id,
            role=actor.role,
            project_id=project_id,
            prompt_id=prompt_id,
            version_id=version_id,
            status=status,
            model=model,
            search=search,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

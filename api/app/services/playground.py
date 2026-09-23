"""Prompt rendering rules shared by playground and run execution."""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from api.app.db.pool import PoolProtocol
from api.app.errors import AppError
from api.app.providers.base import ProviderRequest, execute_with_timeout
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError
from api.app.providers.factory import get_provider
from api.app.repositories.pricing import EffectivePrice, PricingRepository
from api.app.repositories.runs import RunRepository, RunTarget
from api.app.repositories.users import UserRecord
from api.app.schemas.common import Page
from api.app.schemas.runs import RunCreate, RunResponse, RunStatus
from api.app.services.budget_enforcement import BudgetEnforcementService
from api.app.services.cost_calculation import calculate_cost
from psycopg import AsyncConnection

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
    ) -> None:
        self.pool = pool
        self.request_id = request_id
        self.provider_timeout_seconds = provider_timeout_seconds

    async def execute(self, payload: RunCreate, actor: UserRecord) -> RunResponse:
        executed_at = datetime.now(UTC)
        target, price = await self._load_target_and_price(
            payload.version_id, actor, executed_at
        )
        try:
            prompt = render_template(target.template_body, target.variables, payload.variables)
        except InvalidVariablesError as exc:
            field_errors: dict[str, list[str]] = {}
            if exc.missing:
                field_errors["body.variables"] = [
                    f"Missing variables: {', '.join(exc.missing)}"
                ]
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
        try:
            result = await execute_with_timeout(
                get_provider(config.provider),
                ProviderRequest(
                    prompt=prompt,
                    model=config.model,
                    temperature=config.temperature,
                    max_output_tokens=config.max_output_tokens,
                ),
                timeout_seconds=self.provider_timeout_seconds,
            )
        except ProviderTimeoutError as exc:
            await self._record_failure(
                actor, target, payload.variables, "provider_timeout", executed_at
            )
            raise AppError(504, "provider_timeout", "Provider request timed out") from exc
        except ProviderExecutionError as exc:
            await self._record_failure(
                actor, target, payload.variables, "provider_error", executed_at
            )
            raise AppError(502, "provider_error", "Provider request failed") from exc
        except Exception as exc:
            await self._record_failure(
                actor, target, payload.variables, "provider_error", executed_at
            )
            raise AppError(502, "provider_error", "Provider request failed") from exc

        cost = calculate_cost(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            input_price_per_million=price.input_price_per_million,
            output_price_per_million=price.output_price_per_million,
        )
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
        if recorded.status == "blocked":
            raise AppError(409, "budget_exceeded", "Monthly budget was exceeded")
        return recorded

    async def _load_target_and_price(
        self,
        version_id: UUID,
        actor: UserRecord,
        executed_at: datetime,
    ) -> tuple[RunTarget, EffectivePrice]:
        async with self.pool.connection() as raw_connection:
            connection = cast(AsyncConnection[dict[str, Any]], raw_connection)
            async with connection.transaction():
                target = await RunRepository(connection).get_target_scoped(
                    version_id, actor.id, actor.role
                )
                if target is None:
                    raise AppError(404, "not_found", "Prompt version was not found")
                config = target.model_configuration
                price = await PricingRepository(connection).get_effective(
                    config.provider,
                    config.model,
                    executed_at,
                )
                if price is None:
                    raise AppError(
                        409,
                        "pricing_not_configured",
                        "Model pricing is not configured",
                    )
                return target, price

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
    ) -> None:
        await self._record(
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
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

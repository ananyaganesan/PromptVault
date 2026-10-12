"""Authenticated discovery for the fixed free-access provider catalog."""

from datetime import UTC, datetime
from typing import Annotated

from api.app.db.transactions import DatabaseConnection, get_connection
from api.app.dependencies.auth import CurrentUser
from api.app.dependencies.query import allow_query_parameters
from api.app.errors import error_responses
from api.app.providers.catalog import MODELS
from api.app.providers.policy import ExternalProvider
from api.app.repositories.pricing import PricingRepository
from api.app.schemas.providers import (
    ProviderDiscoveryResponse,
    ProviderModelResponse,
    ProviderResponse,
)
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get(
    "/models",
    response_model=ProviderDiscoveryResponse,
    responses=error_responses(401, 403, 422),
    dependencies=[Depends(allow_query_parameters())],
)
async def discover_models(
    request: Request,
    current_user: CurrentUser,
    connection: Annotated[DatabaseConnection, Depends(get_connection)],
) -> ProviderDiscoveryResponse:
    cursor = await connection.execute(
        "SELECT DISTINCT provider FROM provider_keys WHERE deactivated_at IS NULL"
    )
    configured = {row["provider"] for row in await cursor.fetchall()}
    items: list[ProviderResponse] = []
    providers: tuple[ExternalProvider, ...] = ("gemini", "openrouter", "groq")
    for provider in providers:
        models: list[ProviderModelResponse] = []
        for model in MODELS:
            if model.provider != provider:
                continue
            price = await PricingRepository(connection).get_effective(
                provider, model.id, datetime.now(UTC)
            )
            reason = "Provider key is not configured" if provider not in configured else None
            if price is not None and (
                price.input_price_per_million != 0 or price.output_price_per_million != 0
            ):
                reason = "Paid model configuration is not allowed"
            models.append(
                ProviderModelResponse(
                    id=model.id,
                    label=model.label,
                    max_output_tokens=model.max_output_tokens,
                    max_input_characters=model.max_input_characters,
                    available=reason is None,
                    unavailable_reason=reason,
                )
            )
        items.append(
            ProviderResponse(
                provider=provider,
                credential_available=provider in configured,
                models=models,
                quota_note=(
                    "Use a free-tier account key. Account quotas apply; no paid fallback is used."
                ),
            )
        )
    return ProviderDiscoveryResponse(
        items=items,
        max_concurrent_runs_per_user=request.app.state.settings.max_concurrent_runs_per_user,
        timeout_seconds=request.app.state.settings.provider_timeout_seconds,
    )

from datetime import UTC, datetime

import pytest
from api.app.errors import AppError
from api.app.providers.catalog import MODELS
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.factory import get_provider
from api.app.providers.policy import EXTERNAL_PROVIDERS, require_allowed_provider
from api.app.schemas.admin import ModelPricingCreate, ProviderKeyCreate
from api.app.schemas.versions import ModelConfiguration
from pydantic import ValidationError


def test_external_provider_scope_is_fixed() -> None:
    assert {"gemini"} == EXTERNAL_PROVIDERS


def test_gemini_catalog_only_exposes_the_demo_model() -> None:
    assert [model.id for model in MODELS if model.provider == "gemini"] == ["gemini-3.5-flash-lite"]


@pytest.mark.parametrize("provider", ["gemini"])
def test_selected_providers_are_valid_for_models_keys_and_pricing(provider: str) -> None:
    require_allowed_provider(provider)
    ModelConfiguration(provider=provider, model="selected-model", max_output_tokens=100)
    ProviderKeyCreate(provider=provider, alias="project", secret="test-secret")
    ModelPricingCreate(
        provider=provider,
        model="selected-model",
        input_price_per_million=0,
        output_price_per_million=0,
        effective_from=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "provider",
    ["mock", "openrouter", "groq", "deepseek", "openai", "anthropic", "unknown", "GEMINI"],
)
def test_other_providers_cannot_be_configured_or_dispatched(provider: str) -> None:
    with pytest.raises(ValidationError):
        ModelConfiguration(provider=provider, model="anything", max_output_tokens=100)
    with pytest.raises(ValidationError):
        ProviderKeyCreate(provider=provider, alias="project", secret="test-secret")
    with pytest.raises(ValidationError):
        ModelPricingCreate(
            provider=provider,
            model="anything",
            input_price_per_million=0,
            output_price_per_million=0,
            effective_from=datetime.now(UTC),
        )
    with pytest.raises(AppError):
        require_allowed_provider(provider)
    with pytest.raises(ProviderExecutionError):
        get_provider(provider, credential="test-secret")

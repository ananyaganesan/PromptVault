"""Removed providers cannot be instantiated in any runtime environment."""

import pytest
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.factory import get_provider


@pytest.mark.parametrize(
    "provider", ["mock", "openrouter", "groq", "openai", "anthropic", "deepseek", "unknown"]
)
def test_removed_providers_have_no_adapter(provider: str) -> None:
    with pytest.raises(ProviderExecutionError, match="Only Gemini"):
        get_provider(provider, credential="not-a-real-key")

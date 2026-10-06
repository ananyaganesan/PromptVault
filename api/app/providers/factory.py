"""Provider selection without exposing provider credentials to callers."""

from api.app.providers.base import Provider
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.gemini import GeminiProvider
from api.app.providers.mock import MockProvider


def get_provider(
    name: str,
    *,
    credential: str | None = None,
    gemini_base_url: str | None = None,
) -> Provider:
    if name == "mock":
        return MockProvider()
    if name == "gemini" and credential:
        if gemini_base_url is None:
            return GeminiProvider(credential)
        return GeminiProvider(credential, base_url=gemini_base_url)
    raise ProviderExecutionError("provider is not configured")

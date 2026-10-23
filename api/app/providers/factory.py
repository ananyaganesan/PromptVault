"""Gemini execution requires a configured credential; no fallback adapters."""

from api.app.providers.base import Provider
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.gemini import GeminiProvider


def get_provider(
    name: str, *, credential: str | None = None, gemini_base_url: str | None = None
) -> Provider:
    if name != "gemini":
        raise ProviderExecutionError("Only Gemini is supported")
    if not credential:
        raise ProviderExecutionError("provider is not configured")
    if gemini_base_url is None:
        return GeminiProvider(credential)
    return GeminiProvider(credential, base_url=gemini_base_url)

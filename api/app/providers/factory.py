"""Provider selection without exposing provider credentials to callers."""

from api.app.providers.base import Provider
from api.app.providers.chat_completions import ChatCompletionsProvider
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.gemini import GeminiProvider
from api.app.providers.mock import MockProvider
from api.app.providers.policy import EXTERNAL_PROVIDERS


def get_provider(
    name: str,
    *,
    credential: str | None = None,
    gemini_base_url: str | None = None,
    allow_mock: bool = False,
) -> Provider:
    if name == "mock" and allow_mock:
        return MockProvider()
    if name not in EXTERNAL_PROVIDERS:
        raise ProviderExecutionError("provider is outside the fixed project scope")
    if name == "gemini" and credential:
        if gemini_base_url is None:
            return GeminiProvider(credential)
        return GeminiProvider(credential, base_url=gemini_base_url)
    if name in {"openrouter", "groq"} and credential:
        return ChatCompletionsProvider("openrouter" if name == "openrouter" else "groq", credential)
    raise ProviderExecutionError("provider is not configured")

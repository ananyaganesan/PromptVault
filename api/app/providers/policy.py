"""Fixed project provider scope. Mock is an internal development/test adapter."""

from typing import Literal

from api.app.errors import AppError

ExternalProvider = Literal["gemini", "openrouter", "groq"]
ConfiguredProvider = Literal["gemini", "openrouter", "groq", "mock"]
EXTERNAL_PROVIDERS = frozenset({"gemini", "openrouter", "groq"})


def require_allowed_provider(provider: str, *, allow_mock: bool = False) -> None:
    if provider in EXTERNAL_PROVIDERS or (provider == "mock" and allow_mock):
        return
    raise AppError(422, "validation_error", "Provider is outside the fixed project scope")

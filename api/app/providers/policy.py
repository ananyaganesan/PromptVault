"""Gemini is the only supported LLM provider in every environment."""

from typing import Literal

from api.app.errors import AppError

ExternalProvider = Literal["gemini"]
ConfiguredProvider = Literal["gemini"]
EXTERNAL_PROVIDERS = frozenset({"gemini"})


def require_allowed_provider(provider: str) -> None:
    if provider != "gemini":
        raise AppError(422, "validation_error", "Only Gemini is supported")

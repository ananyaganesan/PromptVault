"""Small reviewed free-tier text catalog; no arbitrary-model or paid fallback."""

from dataclasses import dataclass

from api.app.errors import AppError
from api.app.providers.policy import ExternalProvider
from api.app.schemas.versions import SavedModelConfiguration


@dataclass(frozen=True, slots=True)
class SupportedModel:
    provider: ExternalProvider
    id: str
    label: str
    max_output_tokens: int = 4096
    max_input_characters: int = 12000


# Reviewed 2026-10-14 against the official pricing/free-plan documentation.
MODELS = (SupportedModel("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),)


def require_free_model(config: SavedModelConfiguration) -> SupportedModel:
    for model in MODELS:
        if (config.provider, config.model) == (model.provider, model.id):
            if config.max_output_tokens > model.max_output_tokens:
                raise AppError(422, "validation_error", "Output limit exceeds this model's limit")
            return model
    raise AppError(409, "model_not_available", "Select a supported free-access model")

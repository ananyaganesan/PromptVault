"""Safe discovery: no credential IDs, ciphertext, secrets or account details."""

from api.app.providers.policy import ExternalProvider
from pydantic import BaseModel


class ProviderModelResponse(BaseModel):
    id: str
    label: str
    max_output_tokens: int
    max_input_characters: int
    free_access: bool = True
    available: bool
    unavailable_reason: str | None = None


class ProviderResponse(BaseModel):
    provider: ExternalProvider
    credential_available: bool
    models: list[ProviderModelResponse]
    quota_note: str


class ProviderDiscoveryResponse(BaseModel):
    items: list[ProviderResponse]
    max_concurrent_runs_per_user: int
    timeout_seconds: float
    credential_ownership: str = "shared_project"

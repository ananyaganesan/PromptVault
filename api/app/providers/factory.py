"""Provider selection without exposing provider credentials to callers."""

from api.app.providers.base import Provider
from api.app.providers.errors import ProviderExecutionError
from api.app.providers.mock import MockProvider


def get_provider(name: str) -> Provider:
    if name == "mock":
        return MockProvider()
    raise ProviderExecutionError("provider is not configured")

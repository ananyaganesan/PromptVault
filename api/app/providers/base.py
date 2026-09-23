"""Provider-neutral request and response contracts."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError

_MAX_PROVIDER_OUTPUT_CHARACTERS = 5_000_000


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    prompt: str
    model: str
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    output_text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class Provider(Protocol):
    async def execute(self, request: ProviderRequest) -> ProviderResult: ...


def validate_provider_result(result: ProviderResult) -> ProviderResult:
    if (
        result.prompt_tokens < 0
        or result.completion_tokens < 0
        or result.latency_ms < 0
        or len(result.output_text) > _MAX_PROVIDER_OUTPUT_CHARACTERS
    ):
        raise ProviderExecutionError("provider returned an invalid result")
    return result


async def execute_with_timeout(
    provider: Provider,
    request: ProviderRequest,
    *,
    timeout_seconds: float,
) -> ProviderResult:
    try:
        result = await asyncio.wait_for(provider.execute(request), timeout=timeout_seconds)
        return validate_provider_result(result)
    except TimeoutError as exc:
        raise ProviderTimeoutError("provider request timed out") from exc

"""Deterministic provider used for development and automated tests."""

import asyncio
import re

from api.app.providers.base import ProviderRequest, ProviderResult
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class MockProvider:
    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.model.startswith("deterministic-timeout"):
            raise ProviderTimeoutError("mock provider timed out")
        if request.model.startswith("deterministic-error"):
            raise ProviderExecutionError("mock provider failed")
        if request.model.startswith("deterministic-crash"):
            raise RuntimeError("unexpected mock provider failure")
        if request.model.startswith("deterministic-delay"):
            await asyncio.sleep(0.2)

        output = f"Mock response: {request.prompt}"
        return ProviderResult(
            output_text=output,
            prompt_tokens=len(_TOKEN_PATTERN.findall(request.prompt)),
            completion_tokens=len(_TOKEN_PATTERN.findall(output)),
            latency_ms=25,
        )

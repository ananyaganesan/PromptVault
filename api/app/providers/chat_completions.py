"""Text-only OpenRouter and Groq adapters using their chat-completions APIs."""

from time import monotonic
from typing import Any, Literal

import httpx
from api.app.providers.base import ProviderRequest, ProviderResult
from api.app.providers.errors import (
    ProviderCredentialError,
    ProviderExecutionError,
    ProviderQuotaError,
    ProviderTimeoutError,
)

ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}


class ChatCompletionsProvider:
    def __init__(self, provider: Literal["openrouter", "groq"], api_key: str) -> None:
        if not api_key:
            raise ProviderExecutionError("provider is not configured")
        self._provider = provider
        self._api_key = api_key

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        started = monotonic()
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        if self._provider == "openrouter":
            if not request.model.endswith(":free"):
                raise ProviderExecutionError("only free OpenRouter models are allowed")
            body["provider"] = {
                "allow_fallbacks": False,
                "max_price": {"prompt": 0, "completion": 0, "request": 0},
            }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    ENDPOINTS[self._provider],
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
                if response.status_code == 429:
                    raise ProviderQuotaError("provider quota reached")
                if response.status_code in {401, 403}:
                    raise ProviderCredentialError("provider credentials were rejected")
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderExecutionError("provider request failed") from exc
        try:
            payload = response.json()
            output = payload["choices"][0]["message"]["content"]
            prompt_tokens = payload["usage"]["prompt_tokens"]
            completion_tokens = payload["usage"]["completion_tokens"]
            if (
                not isinstance(output, str)
                or not output.strip()
                or type(prompt_tokens) is not int
                or prompt_tokens < 0
                or type(completion_tokens) is not int
                or completion_tokens < 0
            ):
                raise ValueError
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ProviderExecutionError("provider returned an invalid response") from exc
        return ProviderResult(
            output_text=output,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=max(0, round((monotonic() - started) * 1000)),
        )

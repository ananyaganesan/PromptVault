"""Gemini REST adapter for text-only prompt execution."""

from __future__ import annotations

from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx
from api.app.providers.base import ProviderRequest, ProviderResult
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    def __init__(self, api_key: str, *, base_url: str = _DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ProviderExecutionError("provider is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        started = monotonic()
        url = (
            f"{self._base_url}/models/{quote(request.model, safe='')}:generateContent"
        )
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json={
                        "contents": [
                            {"role": "user", "parts": [{"text": request.prompt}]}
                        ],
                        "generationConfig": {
                            "temperature": request.temperature,
                            "maxOutputTokens": request.max_output_tokens,
                        },
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderExecutionError("provider request failed") from exc

        try:
            payload: Any = response.json()
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            output = "".join(part["text"] for part in parts if "text" in part)
            usage = payload["usageMetadata"]
            prompt_tokens = usage["promptTokenCount"]
            completion_tokens = usage["candidatesTokenCount"]
            if (
                not output
                or not isinstance(prompt_tokens, int)
                or not isinstance(completion_tokens, int)
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

"""Gemini REST adapter for text-only prompt execution."""

from __future__ import annotations

import json
import math
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx
from api.app.providers.base import ProviderRequest, ProviderResult
from api.app.providers.errors import (
    ProviderCredentialError,
    ProviderExecutionError,
    ProviderModelError,
    ProviderQuotaError,
    ProviderTimeoutError,
)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    def __init__(self, api_key: str, *, base_url: str = _DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ProviderExecutionError("provider is not configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        started = monotonic()
        url = f"{self._base_url}/models/{quote(request.model, safe='')}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
                        "generationConfig": {
                            "temperature": request.temperature,
                            "maxOutputTokens": request.max_output_tokens,
                        },
                    },
                )
                if response.status_code == 429:
                    raise ProviderQuotaError("provider quota reached")
                if response.status_code in {401, 403}:
                    raise ProviderCredentialError("provider credentials were rejected")
                if response.status_code == 404:
                    raise ProviderModelError("provider model is unavailable")
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
            if not output or type(prompt_tokens) is not int or type(completion_tokens) is not int:
                raise ValueError
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ProviderExecutionError("provider returned an invalid response") from exc

        return ProviderResult(
            output_text=output,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=max(0, round((monotonic() - started) * 1000)),
        )


# Reviewed against https://ai.google.dev/gemini-api/docs/pricing on 2026-10-28.
# Separate from selectable text-generation models; no paid/model fallback.
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768


class GeminiEmbeddingProvider(GeminiProvider):
    """Single-text semantic embeddings through Gemini's standard free-access endpoint."""

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.model != EMBEDDING_MODEL or not request.prompt.strip():
            raise ProviderModelError("invalid embedding request")
        started = monotonic()
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{self._base_url}/models/{EMBEDDING_MODEL}:embedContent",
                    headers={"x-goog-api-key": self._api_key},
                    json={
                        "model": f"models/{EMBEDDING_MODEL}",
                        "content": {
                            "parts": [
                                {"text": f"task: sentence similarity | query: {request.prompt}"}
                            ]
                        },
                        "outputDimensionality": EMBEDDING_DIMENSIONS,
                    },
                )
                if response.status_code == 429:
                    raise ProviderQuotaError("provider quota reached")
                if response.status_code in {401, 403}:
                    raise ProviderCredentialError("provider credentials were rejected")
                if response.status_code == 404:
                    raise ProviderModelError("provider model is unavailable")
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderExecutionError("provider request failed") from exc
        try:
            payload = response.json()
            values = payload["embedding"]["values"]
            if (
                not isinstance(values, list)
                or len(values) != EMBEDDING_DIMENSIONS
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or not any(values)
            ):
                raise ValueError("invalid vector")
            tokens = payload.get("usageMetadata", {}).get("promptTokenCount", 0)
            if type(tokens) is not int or tokens < 0:
                raise ValueError("invalid usage")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderExecutionError("provider returned an invalid embedding") from exc
        return ProviderResult(
            output_text=json.dumps(values),
            prompt_tokens=tokens,
            completion_tokens=0,
            latency_ms=max(0, round((monotonic() - started) * 1000)),
        )

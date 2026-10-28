"""Gemini embedding REST contract and invalid-response handling."""

import httpx
import pytest
from api.app.providers.base import ProviderRequest
from api.app.providers.errors import (
    ProviderCredentialError,
    ProviderExecutionError,
    ProviderModelError,
    ProviderQuotaError,
)
from api.app.providers.gemini import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    GeminiEmbeddingProvider,
)


async def call(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler))
    )
    return await GeminiEmbeddingProvider("test-key").execute(
        ProviderRequest("Trusted answer", EMBEDDING_MODEL, 0, 0)
    )


async def test_embedding_rest_contract(monkeypatch):
    import json

    def handler(request):
        assert str(request.url).endswith(f"/models/{EMBEDDING_MODEL}:embedContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        assert body["outputDimensionality"] == EMBEDDING_DIMENSIONS
        assert body["content"]["parts"][0]["text"] == (
            "task: sentence similarity | query: Trusted answer"
        )
        assert "taskType" not in body
        return httpx.Response(200, json={"embedding": {"values": [1.0] * EMBEDDING_DIMENSIONS}})

    result = await call(monkeypatch, handler)
    assert len(json.loads(result.output_text)) == EMBEDDING_DIMENSIONS
    assert result.completion_tokens == 0


@pytest.mark.parametrize(
    "status,error",
    [
        (429, ProviderQuotaError),
        (403, ProviderCredentialError),
        (404, ProviderModelError),
        (500, ProviderExecutionError),
    ],
)
async def test_embedding_errors_do_not_fall_back(monkeypatch, status, error):
    with pytest.raises(error):
        await call(monkeypatch, lambda request: httpx.Response(status))


@pytest.mark.parametrize(
    "values", [[], [1], [0] * EMBEDDING_DIMENSIONS, [True] * EMBEDDING_DIMENSIONS]
)
async def test_invalid_embedding_is_rejected(monkeypatch, values):
    with pytest.raises(ProviderExecutionError):
        await call(
            monkeypatch, lambda request: httpx.Response(200, json={"embedding": {"values": values}})
        )

import json

import httpx
import pytest
from api.app.providers.base import ProviderRequest
from api.app.providers.chat_completions import ChatCompletionsProvider
from api.app.providers.errors import (
    ProviderCredentialError,
    ProviderExecutionError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from api.app.providers.factory import get_provider


@pytest.mark.parametrize(
    "provider,model,host",
    [
        ("openrouter", "liquid/lfm-2.5-2.6b:free", "openrouter.ai"),
        ("groq", "qwen/qwen3.8-27b", "api.groq.com"),
    ],
)
async def test_chat_adapter_contract_and_zero_price_routing(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
    host: str,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == host
        assert request.headers["Authorization"] == "Bearer hidden-project-key"
        payload = json.loads(request.content)
        assert payload["model"] == model
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["max_tokens"] == 100
        assert payload["stream"] is False
        if provider == "openrouter":
            assert payload["provider"] == {
                "allow_fallbacks": False,
                "max_price": {"prompt": 0, "completion": 0, "request": 0},
            }
            assert "models" not in payload
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Response"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(handle))
    )
    result = await get_provider(provider, credential="hidden-project-key").execute(
        ProviderRequest("Hello", model, 0, 100),
    )
    assert result.output_text == "Response"
    assert result.prompt_tokens == 7 and result.completion_tokens == 3
    assert result.latency_ms >= 0


@pytest.mark.parametrize(
    "status,error",
    [
        (429, ProviderQuotaError),
        (401, ProviderCredentialError),
        (403, ProviderCredentialError),
        (500, ProviderExecutionError),
    ],
)
async def test_chat_adapter_normalizes_errors_without_exposing_body(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    error: type[Exception],
) -> None:
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text="private-secret"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=transport))
    with pytest.raises(error) as caught:
        await ChatCompletionsProvider("groq", "hidden-key").execute(
            ProviderRequest("Hello", "qwen/qwen3.8-27b", 0, 100),
        )
    assert "private-secret" not in str(caught.value) and "hidden-key" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {
            "choices": [{"message": {"content": ""}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        {
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"prompt_tokens": True, "completion_tokens": -1},
        },
    ],
)
async def test_chat_adapter_rejects_malformed_usage(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=transport))
    with pytest.raises(ProviderExecutionError):
        await ChatCompletionsProvider("groq", "hidden-key").execute(
            ProviderRequest("Hello", "qwen/qwen3.8-27b", 0, 100),
        )


async def test_chat_adapter_timeout_and_paid_openrouter_are_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private-secret", request=request)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(handle))
    )
    with pytest.raises(ProviderTimeoutError):
        await ChatCompletionsProvider("groq", "hidden-key").execute(
            ProviderRequest("Hello", "qwen/qwen3.8-27b", 0, 100),
        )
    with pytest.raises(ProviderExecutionError, match="only free"):
        await ChatCompletionsProvider("openrouter", "hidden-key").execute(
            ProviderRequest("Hello", "paid/model", 0, 100),
        )

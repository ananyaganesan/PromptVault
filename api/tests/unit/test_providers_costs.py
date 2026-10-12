import asyncio
import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from api.app.providers.base import (
    ProviderRequest,
    ProviderResult,
    execute_with_timeout,
    validate_provider_result,
)
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError
from api.app.providers.factory import get_provider
from api.app.providers.gemini import GeminiProvider
from api.app.providers.mock import MockProvider
from api.app.services.cost_calculation import calculate_cost
from api.app.services.playground import (
    InvalidVariablesError,
    PromptRenderLimitError,
    render_template,
)


@pytest.mark.asyncio
async def test_mock_provider_returns_stable_output_usage_and_latency() -> None:
    result = await MockProvider().execute(
        ProviderRequest(
            prompt="Hello Jobin.",
            model="deterministic-v1",
            temperature=0,
            max_output_tokens=100,
        )
    )

    assert result.output_text == "Mock response: Hello Jobin."
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 6
    assert result.latency_ms == 25


@pytest.mark.asyncio
async def test_mock_provider_can_pause_deterministically_for_race_tests() -> None:
    task = asyncio.create_task(
        MockProvider().execute(
            ProviderRequest(
                prompt="Hello",
                model="deterministic-delay",
                temperature=0,
                max_output_tokens=100,
            )
        )
    )
    await asyncio.sleep(0.01)
    assert task.done() is False
    result = await task
    assert result.output_text == "Mock response: Hello"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "error_type"),
    [
        ("deterministic-error", ProviderExecutionError),
        ("deterministic-timeout", ProviderTimeoutError),
    ],
)
async def test_mock_provider_has_deterministic_failure_modes(
    model: str,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        await MockProvider().execute(
            ProviderRequest(
                prompt="Hello",
                model=model,
                temperature=0,
                max_output_tokens=100,
            )
        )


@pytest.mark.asyncio
async def test_provider_execution_is_bounded_by_timeout() -> None:
    class HangingProvider:
        async def execute(self, request: ProviderRequest):
            await asyncio.sleep(1)

    with pytest.raises(ProviderTimeoutError):
        await execute_with_timeout(
            HangingProvider(),
            ProviderRequest(
                prompt="Hello",
                model="slow",
                temperature=0,
                max_output_tokens=100,
            ),
            timeout_seconds=0.001,
        )


@pytest.mark.parametrize(
    "result",
    [
        ProviderResult("ok", -1, 1, 1),
        ProviderResult("ok", 1, -1, 1),
        ProviderResult("ok", 1, 1, -1),
        ProviderResult("x" * 5_000_001, 1, 1, 1),
    ],
)
def test_provider_results_must_be_bounded_and_nonnegative(result: ProviderResult) -> None:
    with pytest.raises(ProviderExecutionError):
        validate_provider_result(result)


def test_provider_factory_rejects_unconfigured_provider() -> None:
    assert isinstance(get_provider("mock", allow_mock=True), MockProvider)
    with pytest.raises(ProviderExecutionError):
        get_provider("gemini")
    with pytest.raises(ProviderExecutionError):
        get_provider("unknown")


@pytest.mark.asyncio
async def test_gemini_provider_sends_secret_header_and_reads_usage() -> None:
    observed: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            observed["path"] = self.path
            observed["api_key"] = self.headers.get("x-goog-api-key")
            observed["body"] = json.loads(self.rfile.read(length))
            body = json.dumps(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "Gemini response"}]}}
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 7,
                        "candidatesTokenCount": 3,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = await GeminiProvider(
            "gemini-secret",
            base_url=f"http://127.0.0.1:{server.server_port}/v1beta",
        ).execute(
            ProviderRequest(
                prompt="Hello Gemini",
                model="gemini-test",
                temperature=0.25,
                max_output_tokens=128,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.output_text == "Gemini response"
    assert result.prompt_tokens == 7
    assert result.completion_tokens == 3
    assert result.latency_ms >= 0
    assert observed == {
        "path": "/v1beta/models/gemini-test:generateContent",
        "api_key": "gemini-secret",
        "body": {
            "contents": [{"role": "user", "parts": [{"text": "Hello Gemini"}]}],
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": 128},
        },
    }


@pytest.mark.asyncio
async def test_gemini_provider_normalizes_http_and_invalid_responses() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path.startswith("/error/"):
                self.send_response(429)
                self.end_headers()
                return
            body = b'{"candidates": [], "usageMetadata": {}}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = ProviderRequest("Hello", "gemini-test", 0, 10)
    try:
        with pytest.raises(ProviderExecutionError):
            await GeminiProvider(
                "secret", base_url=f"http://127.0.0.1:{server.server_port}/error"
            ).execute(request)
        with pytest.raises(ProviderExecutionError):
            await GeminiProvider(
                "secret", base_url=f"http://127.0.0.1:{server.server_port}/invalid"
            ).execute(request)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_template_rendering_requires_exact_variables_and_replaces_repeats() -> None:
    assert render_template(
        "Hello {{name}}; again {{ name }}.",
        ["name"],
        {"name": "Jobin"},
    ) == "Hello Jobin; again Jobin."

    with pytest.raises(InvalidVariablesError) as missing:
        render_template("Hello {{name}}", ["name"], {})
    assert missing.value.missing == ["name"]
    assert missing.value.extra == []

    with pytest.raises(InvalidVariablesError) as extra:
        render_template("Hello {{name}}", ["name"], {"name": "Jobin", "admin": "true"})
    assert extra.value.missing == []
    assert extra.value.extra == ["admin"]


def test_template_rendering_rejects_amplified_output_before_allocation() -> None:
    with pytest.raises(PromptRenderLimitError):
        render_template("{{value}}" * 1_001, ["value"], {"value": "x"})

    with pytest.raises(PromptRenderLimitError):
        render_template("{{value}}" * 3, ["value"], {"value": "x" * 100_000})


def test_cost_calculation_uses_decimal_prices_and_six_place_rounding() -> None:
    assert calculate_cost(
        prompt_tokens=3,
        completion_tokens=6,
        input_price_per_million=Decimal("1.000000"),
        output_price_per_million=Decimal("2.000000"),
    ) == Decimal("0.000015")
    assert calculate_cost(
        prompt_tokens=1,
        completion_tokens=1,
        input_price_per_million=Decimal("0.333333"),
        output_price_per_million=Decimal("0.333333"),
    ) == Decimal("0.000001")

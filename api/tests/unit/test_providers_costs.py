import asyncio
from decimal import Decimal

import pytest
from api.app.providers.base import (
    ProviderRequest,
    ProviderResult,
    execute_with_timeout,
    validate_provider_result,
)
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError
from api.app.providers.factory import get_provider
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
    assert isinstance(get_provider("mock"), MockProvider)
    with pytest.raises(ProviderExecutionError):
        get_provider("unknown")


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

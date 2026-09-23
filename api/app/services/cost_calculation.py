"""Precise token-cost calculations."""

from decimal import ROUND_HALF_UP, Decimal

_MILLION = Decimal("1000000")
_COST_QUANTUM = Decimal("0.000001")


def calculate_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_price_per_million: Decimal,
    output_price_per_million: Decimal,
) -> Decimal:
    cost = (
        Decimal(prompt_tokens) * input_price_per_million
        + Decimal(completion_tokens) * output_price_per_million
    ) / _MILLION
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)

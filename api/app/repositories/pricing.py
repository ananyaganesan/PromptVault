"""Effective-dated model pricing persistence."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class EffectivePrice:
    input_price_per_million: Decimal
    output_price_per_million: Decimal


class PricingRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def get_effective(
        self,
        provider: str,
        model: str,
        at: datetime,
    ) -> EffectivePrice | None:
        cursor = await self.connection.execute(
            """
            SELECT input_price_per_million, output_price_per_million
            FROM model_pricing
            WHERE provider = %s
              AND model = %s
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to > %s)
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (provider, model, at, at),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return EffectivePrice(
            input_price_per_million=row["input_price_per_million"],
            output_price_per_million=row["output_price_per_million"],
        )

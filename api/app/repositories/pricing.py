"""Effective-dated model pricing persistence."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from api.app.db.models import ModelPrice
from api.app.db.orm import ORMConnection, orm_one
from sqlalchemy import or_, select


@dataclass(frozen=True, slots=True)
class EffectivePrice:
    input_price_per_million: Decimal
    output_price_per_million: Decimal


class PricingRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def get_effective(
        self,
        provider: str,
        model: str,
        at: datetime,
    ) -> EffectivePrice | None:
        row = await orm_one(
            self.connection,
            select(ModelPrice.input_price_per_million, ModelPrice.output_price_per_million)
            .where(
                ModelPrice.provider == provider,
                ModelPrice.model == model,
                ModelPrice.effective_from <= at,
                or_(ModelPrice.effective_to.is_(None), ModelPrice.effective_to > at),
            )
            .order_by(ModelPrice.effective_from.desc())
            .limit(1),
        )
        return EffectivePrice(**row) if row else None

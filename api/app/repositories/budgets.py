"""Budget lookup persistence."""

from decimal import Decimal
from uuid import UUID

from api.app.db.models import Budget
from api.app.db.orm import ORMConnection, orm_one
from sqlalchemy import select


class BudgetRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def get_user_limit(self, user_id: UUID) -> tuple[Decimal | None, str]:
        row = await orm_one(
            self.connection,
            select(Budget.monthly_limit, Budget.timezone).where(Budget.user_id == user_id),
        )
        return (row["monthly_limit"], row["timezone"]) if row else (None, "UTC")

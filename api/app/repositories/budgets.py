"""Budget lookup persistence."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection


class BudgetRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def get_user_limit(self, user_id: UUID) -> tuple[Decimal | None, str]:
        cursor = await self.connection.execute(
            """
            SELECT monthly_limit, timezone
            FROM budgets
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None, "UTC"
        return row["monthly_limit"], row["timezone"]

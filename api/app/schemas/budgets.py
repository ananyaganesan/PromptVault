"""Budget data shared by run enforcement and administration."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class BudgetResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    project_id: UUID | None
    monthly_limit: Decimal
    timezone: str

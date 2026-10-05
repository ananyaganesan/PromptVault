"""Atomic run recording through the database budget boundary."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from api.app.repositories.runs import RunRepository, RunTarget
from api.app.schemas.runs import RunResponse, RunStatus


class BudgetEnforcementService:
    def __init__(self, runs: RunRepository) -> None:
        self.runs = runs

    async def record_run(
        self,
        *,
        user_id: UUID,
        target: RunTarget,
        status: RunStatus,
        input_variables: dict[str, str],
        output_text: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        cost: Decimal,
        error_code: str | None,
        request_id: str,
        created_at: datetime,
    ) -> RunResponse:
        return await self.runs.record(
            user_id=user_id,
            target=target,
            status=status,
            input_variables=input_variables,
            output_text=output_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost=cost,
            error_code=error_code,
            request_id=request_id,
            created_at=created_at,
        )

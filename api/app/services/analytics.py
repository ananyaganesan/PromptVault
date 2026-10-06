"""Live personal dashboard aggregation."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.app.errors import AppError
from api.app.repositories.budgets import BudgetRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.users import UserRecord
from api.app.schemas.runs import CostTrendPoint, PersonalDashboardResponse

_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


class AnalyticsService:
    def __init__(self, runs: RunRepository, budgets: BudgetRepository) -> None:
        self.runs = runs
        self.budgets = budgets

    async def personal_dashboard(
        self,
        actor: UserRecord,
        month: str | None,
    ) -> PersonalDashboardResponse:
        monthly_budget, timezone_name = await self.budgets.get_user_limit(actor.id)
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise RuntimeError("stored budget timezone is invalid") from exc

        now = datetime.now(UTC)
        if month is None:
            local_now = now.astimezone(timezone)
            year, month_number = local_now.year, local_now.month
        else:
            match = _MONTH_PATTERN.fullmatch(month)
            if match is None:
                raise AppError(400, "invalid_filter", "Query filter is invalid")
            year, month_number = int(match.group(1)), int(match.group(2))
            if not 1 <= year <= 9998 or not 1 <= month_number <= 12:
                raise AppError(400, "invalid_filter", "Query filter is invalid")

        month_start = datetime(year, month_number, 1, tzinfo=timezone)
        if month_number == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone)
        else:
            month_end = datetime(year, month_number + 1, 1, tzinfo=timezone)
        start_utc = month_start.astimezone(UTC)
        end_utc = month_end.astimezone(UTC)
        metrics = await self.runs.personal_metrics(
            user_id=actor.id,
            month_start=start_utc,
            month_end=end_utc,
        )
        trend_rows = await self.runs.personal_cost_trend(
            user_id=actor.id,
            month_start=start_utc,
            month_end=end_utc,
            timezone=timezone_name,
        )
        return PersonalDashboardResponse(
            month=f"{year:04d}-{month_number:02d}",
            timezone=timezone_name,
            project_count=metrics["project_count"],
            prompt_count=metrics["prompt_count"],
            run_count=metrics["run_count"],
            completed_run_count=metrics["completed_run_count"],
            failed_run_count=metrics["failed_run_count"],
            blocked_run_count=metrics["blocked_run_count"],
            monthly_spend=metrics["monthly_spend"],
            monthly_budget=monthly_budget,
            pending_approval_count=metrics["pending_approval_count"],
            cost_trend=[CostTrendPoint.model_validate(row) for row in trend_rows],
            recent_runs=await self.runs.recent_for_user(actor.id),
            refreshed_through=now,
        )

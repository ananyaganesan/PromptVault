"""Super Admin governance orchestration."""

import re
from datetime import UTC, datetime
from uuid import UUID

from api.app.errors import AppError
from api.app.repositories.admin import AdminRepository
from api.app.repositories.users import UserRecord
from api.app.schemas.admin import (
    AdminCostTrendPoint,
    AdminDashboardResponse,
    AdminUserResponse,
    AdminUserUpdate,
    MaintenanceJobStatus,
    MaintenanceStatusResponse,
    MaterializedViewStatus,
    ModelPricingCreate,
    ModelPricingResponse,
    ModelSpendResponse,
    PartitionCreateResponse,
    ProviderKeyCreate,
    ProviderKeyResponse,
    RunPartitionStatus,
    TopSpenderResponse,
    ViewRefreshResponse,
)
from api.app.schemas.budgets import BudgetCreate, BudgetResponse, BudgetUpdate
from api.app.schemas.common import Page
from api.app.schemas.runs import RunResponse, RunStatus
from api.app.security import encrypt_provider_secret
from api.app.services.time_filters import normalize_datetime_window
from psycopg.errors import (
    CheckViolation,
    ExclusionViolation,
    ForeignKeyViolation,
    InsufficientPrivilege,
    NoDataFound,
    UniqueViolation,
)

_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


def _month_window(month: str | None) -> tuple[str, datetime, datetime]:
    now = datetime.now(UTC)
    if month is None:
        year, month_number = now.year, now.month
    else:
        match = _MONTH_PATTERN.fullmatch(month)
        if match is None:
            raise AppError(400, "invalid_filter", "Query filter is invalid")
        year, month_number = int(match.group(1)), int(match.group(2))
        if not 1 <= year <= 9998 or not 1 <= month_number <= 12:
            raise AppError(400, "invalid_filter", "Query filter is invalid")
    start = datetime(year, month_number, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month_number == 12
        else datetime(year, month_number + 1, 1, tzinfo=UTC)
    )
    return f"{year:04d}-{month_number:02d}", start, end


class AdminGovernanceService:
    def __init__(
        self,
        repository: AdminRepository,
        request_id: str,
        provider_encryption_key: str,
    ) -> None:
        self.repository = repository
        self.request_id = request_id
        self.provider_encryption_key = provider_encryption_key

    async def list_users(
        self,
        *,
        search: str | None,
        role: str | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> Page[AdminUserResponse]:
        items, total = await self.repository.list_users(
            search=search.strip() if search else None,
            role=role,
            is_active=is_active,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def update_user(
        self,
        user_id: UUID,
        payload: AdminUserUpdate,
        actor: UserRecord,
    ) -> AdminUserResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            return await self.repository.update_user(
                user_id,
                actor.id,
                role=payload.role,
                role_set="role" in payload.model_fields_set,
                is_active=payload.is_active,
                active_set="is_active" in payload.model_fields_set,
            )
        except NoDataFound as exc:
            raise AppError(404, "not_found", "User was not found") from exc
        except InsufficientPrivilege as exc:
            raise AppError(
                403, "forbidden", "Super Admin authorization changed during the request"
            ) from exc
        except CheckViolation as exc:
            if "self_lockout" in str(exc):
                raise AppError(
                    409, "conflict", "A Super Admin cannot deactivate or demote themself"
                ) from exc
            if "last_admin" in str(exc) or "last active admin" in str(exc):
                raise AppError(
                    409, "last_admin", "The last active Super Admin cannot be changed"
                ) from exc
            raise AppError(409, "conflict", "User transition is not allowed") from exc

    async def dashboard(self, month: str | None) -> AdminDashboardResponse:
        month_name, start, end = _month_window(month)
        metrics = await self.repository.dashboard_metrics(start, end)
        return AdminDashboardResponse(
            month=month_name,
            timezone="UTC",
            **metrics,
            spend_by_model=[
                ModelSpendResponse.model_validate(row)
                for row in await self.repository.spend_by_model(start, end)
            ],
            cost_trend=[
                AdminCostTrendPoint.model_validate(row)
                for row in await self.repository.cost_trend(start, end)
            ],
            top_spenders=[
                TopSpenderResponse.model_validate(row)
                for row in await self.repository.top_spenders(start, end)
            ],
            refreshed_through=datetime.now(UTC),
        )

    async def list_runs(
        self,
        *,
        search: str | None,
        user_id: UUID | None,
        project_id: UUID | None,
        prompt_id: UUID | None,
        model: str | None,
        status: RunStatus | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> Page[RunResponse]:
        created_from, created_to = normalize_datetime_window(created_from, created_to)
        items, total = await self.repository.list_runs(
            search=search,
            user_id=user_id,
            project_id=project_id,
            prompt_id=prompt_id,
            model=model,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def list_budgets(
        self,
        *,
        user_id: UUID | None,
        project_id: UUID | None,
        page: int,
        page_size: int,
    ) -> Page[BudgetResponse]:
        items, total = await self.repository.list_budgets(
            user_id=user_id, project_id=project_id, page=page, page_size=page_size
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def create_budget(
        self, payload: BudgetCreate, actor: UserRecord
    ) -> BudgetResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            return await self.repository.create_budget(
                user_id=payload.user_id,
                project_id=payload.project_id,
                monthly_limit=payload.monthly_limit,
                timezone=payload.timezone,
                actor_id=actor.id,
            )
        except ForeignKeyViolation as exc:
            raise AppError(404, "not_found", "Budget target was not found") from exc
        except UniqueViolation as exc:
            raise AppError(409, "conflict", "Budget already exists for this target") from exc

    async def update_budget(
        self, budget_id: UUID, payload: BudgetUpdate, actor: UserRecord
    ) -> BudgetResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        updated = await self.repository.update_budget(
            budget_id,
            monthly_limit=payload.monthly_limit,
            limit_set="monthly_limit" in payload.model_fields_set,
            timezone=payload.timezone,
            timezone_set="timezone" in payload.model_fields_set,
        )
        if updated is None:
            raise AppError(404, "not_found", "Budget was not found")
        return updated

    async def delete_budget(self, budget_id: UUID, actor: UserRecord) -> None:
        await self.repository.set_audit_context(actor.id, self.request_id)
        if not await self.repository.delete_budget(budget_id):
            raise AppError(404, "not_found", "Budget was not found")

    async def list_provider_keys(
        self, *, provider: str | None, page: int, page_size: int
    ) -> Page[ProviderKeyResponse]:
        items, total = await self.repository.list_provider_keys(
            provider=provider, page=page, page_size=page_size
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def create_provider_key(
        self, payload: ProviderKeyCreate, actor: UserRecord
    ) -> ProviderKeyResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            return await self.repository.create_provider_key(
                payload.provider,
                payload.alias,
                encrypt_provider_secret(payload.secret, self.provider_encryption_key),
                actor.id,
            )
        except UniqueViolation as exc:
            raise AppError(409, "conflict", "Active provider-key alias already exists") from exc

    async def deactivate_provider_key(self, key_id: UUID, actor: UserRecord) -> None:
        await self.repository.set_audit_context(actor.id, self.request_id)
        if not await self.repository.deactivate_provider_key(key_id):
            raise AppError(404, "not_found", "Active provider key was not found")

    async def list_pricing(
        self,
        *,
        provider: str | None,
        model: str | None,
        page: int,
        page_size: int,
    ) -> Page[ModelPricingResponse]:
        items, total = await self.repository.list_pricing(
            provider=provider, model=model, page=page, page_size=page_size
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

    async def create_pricing(
        self, payload: ModelPricingCreate, actor: UserRecord
    ) -> ModelPricingResponse:
        await self.repository.set_audit_context(actor.id, self.request_id)
        try:
            return await self.repository.create_pricing(
                provider=payload.provider,
                model=payload.model,
                input_price=payload.input_price_per_million,
                output_price=payload.output_price_per_million,
                effective_from=payload.effective_from,
                effective_to=payload.effective_to,
                actor_id=actor.id,
            )
        except ExclusionViolation as exc:
            raise AppError(409, "conflict", "Pricing window overlaps existing history") from exc

    async def maintenance_status(self) -> MaintenanceStatusResponse:
        status = await self.repository.maintenance_status()
        return MaintenanceStatusResponse(
            database="ok",
            materialized_views=[
                MaterializedViewStatus.model_validate(row)
                for row in status["materialized_views"]
            ],
            run_partitions=[
                RunPartitionStatus.model_validate(row) for row in status["run_partitions"]
            ],
            maintenance_jobs=[
                MaintenanceJobStatus(
                    name="refresh_materialized_views",
                    status="completed" if status["last_view_refresh_at"] else "never_run",
                    last_completed_at=status["last_view_refresh_at"],
                ),
                MaintenanceJobStatus(
                    name="create_next_partition",
                    status=(
                        "completed" if status["last_partition_creation_at"] else "never_run"
                    ),
                    last_completed_at=status["last_partition_creation_at"],
                ),
            ],
            active_provider_key_count=status["active_provider_key_count"],
            pending_deployment_count=status["pending_deployment_count"],
            checked_at=datetime.now(UTC),
        )

    async def refresh_views(self, actor: UserRecord) -> ViewRefreshResponse:
        try:
            completed_at = await self.repository.refresh_views(actor.id, self.request_id)
        except InsufficientPrivilege as exc:
            raise AppError(
                403, "forbidden", "Super Admin authorization changed during the request"
            ) from exc
        return ViewRefreshResponse(
            status="completed",
            views=["organization_monthly_metrics", "user_monthly_metrics"],
            completed_at=completed_at,
        )

    async def create_next_partition(self, actor: UserRecord) -> PartitionCreateResponse:
        try:
            name, existed = await self.repository.create_next_partition(
                actor.id, self.request_id
            )
        except InsufficientPrivilege as exc:
            raise AppError(
                403, "forbidden", "Super Admin authorization changed during the request"
            ) from exc
        return PartitionCreateResponse(partition_name=name, already_existed=existed)

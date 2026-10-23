"""Super Admin governance persistence."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from api.app.db.models import (
    AuthSession,
    Budget,
    ModelPrice,
    ProjectMember,
    ProviderKey,
    User,
    fields,
)
from api.app.db.orm import ORMConnection, execute_orm, orm_one, orm_page
from api.app.repositories.pagination import read_page
from api.app.schemas.admin import (
    AdminUserResponse,
    ModelPricingResponse,
    ProviderKeyResponse,
)
from api.app.schemas.budgets import BudgetResponse
from api.app.schemas.runs import RunResponse, RunStatus
from sqlalchemy import delete, func, insert, select, update

_RUN_COLUMNS = """
    r.id, r.user_id, r.project_id, r.prompt_id, p.key AS prompt_key,
    r.version_id, pv.version_number, r.status, r.provider, r.model,
    r.input_variables, left(r.output_text, 2000) AS output_text,
    r.prompt_tokens, r.completion_tokens, r.latency_ms, r.cost,
    r.error_code, r.created_at
"""


def _admin_user(row: Mapping[str, Any]) -> AdminUserResponse:
    return AdminUserResponse.model_validate(row)


def _budget(row: Mapping[str, Any]) -> BudgetResponse:
    return BudgetResponse.model_validate(row)


def _provider_key(row: Mapping[str, Any]) -> ProviderKeyResponse:
    return ProviderKeyResponse.model_validate(row)


def _pricing(row: Mapping[str, Any]) -> ModelPricingResponse:
    return ModelPricingResponse.model_validate(row)


def _run(row: Mapping[str, Any]) -> RunResponse:
    return RunResponse.model_validate(row)


class AdminRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def set_audit_context(self, actor_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), set_config('app.request_id', %s, true)",
            (str(actor_id), request_id),
        )

    async def list_users(
        self,
        *,
        search: str | None,
        role: str | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminUserResponse], int]:
        where = ["TRUE"]
        parameters: list[Any] = []
        if search:
            where.append("(u.email ILIKE %s OR u.display_name ILIKE %s)")
            parameters.extend([f"%{search}%", f"%{search}%"])
        if role is not None:
            where.append("u.role = %s")
            parameters.append(role)
        if is_active is not None:
            where.append("u.is_active = %s")
            parameters.append(is_active)
        where_sql = " AND ".join(where)
        count_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM users u WHERE {where_sql}",
            tuple(parameters),
        )
        total_row = await count_cursor.fetchone()
        if total_row is None:
            raise RuntimeError("user count returned no row")
        cursor = await self.connection.execute(
            f"""
            SELECT u.id, u.email, u.display_name, u.role, u.is_active,
                   count(pm.project_id)::integer AS project_count,
                   u.created_at, u.updated_at
            FROM users u
            LEFT JOIN project_members pm ON pm.user_id = u.id
            WHERE {where_sql}
            GROUP BY u.id
            ORDER BY u.created_at DESC, u.id DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, page_size, (page - 1) * page_size),
        )
        return [_admin_user(row) for row in await cursor.fetchall()], int(total_row["total"])

    async def get_user(self, user_id: UUID) -> AdminUserResponse | None:
        project_count = (
            select(func.count())
            .where(ProjectMember.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        row = await orm_one(
            self.connection,
            select(
                User.id,
                User.email,
                User.display_name,
                User.role,
                User.is_active,
                User.created_at,
                User.updated_at,
                project_count.label("project_count"),
            ).where(User.id == user_id),
        )
        return _admin_user(row) if row else None

    async def update_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        *,
        role: str | None,
        role_set: bool,
        is_active: bool | None,
        active_set: bool,
    ) -> AdminUserResponse:
        cursor = await self.connection.execute(
            """
            SELECT (admin_update_user(
                p_target_user_id => %s, p_actor_user_id => %s,
                p_role => %s::user_role, p_role_set => %s,
                p_is_active => %s, p_active_set => %s
            )).id AS id
            """,
            (user_id, actor_id, role, role_set, is_active, active_set),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("user update function returned no row")
        if role_set or active_set:
            await execute_orm(
                self.connection,
                update(AuthSession)
                .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=func.current_timestamp(), revocation_reason="account_changed"),
            )
        updated = await self.get_user(row["id"])
        if updated is None:
            raise RuntimeError("updated user was not returned")
        return updated

    async def dashboard_metrics(
        self, month_start: datetime, month_end: datetime
    ) -> Mapping[str, Any]:
        cursor = await self.connection.execute(
            """
            SELECT
                (SELECT count(*) FROM users) AS user_count,
                (SELECT count(*) FROM users WHERE is_active) AS active_user_count,
                (SELECT count(*) FROM projects) AS project_count,
                (SELECT count(*) FROM prompts) AS prompt_count,
                (SELECT count(*) FROM deployment_context WHERE status = 'pending')
                    AS pending_approval_count,
                count(*) AS run_count,
                count(*) FILTER (WHERE status = 'completed') AS completed_run_count,
                count(*) FILTER (WHERE status = 'failed') AS failed_run_count,
                count(*) FILTER (WHERE status = 'blocked') AS blocked_run_count,
                COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0) AS total_spend
            FROM run_context
            WHERE created_at >= %s AND created_at < %s
            """,
            (month_start, month_end),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("organization dashboard returned no row")
        return row

    async def spend_by_model(
        self, month_start: datetime, month_end: datetime
    ) -> list[Mapping[str, Any]]:
        cursor = await self.connection.execute(
            """
            SELECT provider, model, count(*)::integer AS run_count,
                   COALESCE(sum(cost), 0) AS cost
            FROM run_context
            WHERE status = 'completed' AND created_at >= %s AND created_at < %s
            GROUP BY provider, model
            ORDER BY cost DESC, provider, model
            LIMIT 20
            """,
            (month_start, month_end),
        )
        return list(await cursor.fetchall())

    async def cost_trend(
        self, month_start: datetime, month_end: datetime
    ) -> list[Mapping[str, Any]]:
        cursor = await self.connection.execute(
            """
            SELECT created_at::date AS date, COALESCE(sum(cost), 0) AS cost,
                   count(*)::integer AS run_count
            FROM run_context
            WHERE status = 'completed' AND created_at >= %s AND created_at < %s
            GROUP BY created_at::date ORDER BY date
            """,
            (month_start, month_end),
        )
        return list(await cursor.fetchall())

    async def top_spenders(
        self, month_start: datetime, month_end: datetime
    ) -> list[Mapping[str, Any]]:
        cursor = await self.connection.execute(
            """
            SELECT u.id AS user_id, u.display_name, COALESCE(sum(r.cost), 0) AS cost
            FROM run_context r JOIN users u ON u.id = r.user_id
            WHERE r.status = 'completed' AND r.created_at >= %s AND r.created_at < %s
            GROUP BY u.id ORDER BY cost DESC, u.id LIMIT 10
            """,
            (month_start, month_end),
        )
        return list(await cursor.fetchall())

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
    ) -> tuple[list[RunResponse], int]:
        where = ["TRUE"]
        parameters: list[Any] = []
        for clause, value in (
            ("r.user_id = %s", user_id),
            ("r.project_id = %s", project_id),
            ("r.prompt_id = %s", prompt_id),
            ("r.model = %s", model),
            ("r.status = %s", status),
            ("r.created_at >= %s", created_from),
            ("r.created_at < %s", created_to),
        ):
            if value is not None:
                where.append(clause)
                parameters.append(value)
        if search is not None:
            escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(p.key ILIKE %s ESCAPE E'\\\\' OR r.id::text ILIKE %s ESCAPE E'\\\\')")
            pattern = f"%{escaped_search}%"
            parameters.extend((pattern, pattern))
        where_sql = " AND ".join(where)
        rows, total = await read_page(
            self.connection,
            count_query=f"""SELECT count(*) AS total
                FROM run_context r
                JOIN prompts p ON p.id = r.prompt_id
                WHERE {where_sql}""",
            items_query=f"""
            SELECT {_RUN_COLUMNS}
            FROM run_context r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN prompt_versions pv ON pv.id = r.version_id
            WHERE {where_sql}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s OFFSET %s
            """,
            parameters=parameters,
            page=page,
            page_size=page_size,
            order_by="created_at DESC, id DESC",
        )
        return [_run(row) for row in rows], total

    async def list_budgets(
        self, *, user_id: UUID | None, project_id: UUID | None, page: int, page_size: int
    ) -> tuple[list[BudgetResponse], int]:
        statement = select(*fields(Budget))
        if user_id is not None:
            statement = statement.where(Budget.user_id == user_id)
        if project_id is not None:
            statement = statement.where(Budget.project_id == project_id)
        rows, total = await orm_page(
            self.connection,
            statement.order_by(Budget.updated_at.desc(), Budget.id.desc()),
            page=page,
            page_size=page_size,
            order=[("updated_at", True), ("id", True)],
        )
        return [_budget(row) for row in rows], total

    async def create_budget(
        self,
        *,
        user_id: UUID | None,
        project_id: UUID | None,
        monthly_limit: Decimal,
        timezone: str,
        actor_id: UUID,
    ) -> BudgetResponse:
        row = await orm_one(
            self.connection,
            insert(Budget)
            .values(
                user_id=user_id,
                project_id=project_id,
                monthly_limit=monthly_limit,
                timezone=timezone,
                created_by=actor_id,
            )
            .returning(*fields(Budget)),
        )
        if row is None:
            raise RuntimeError("budget insert returned no row")
        return _budget(row)

    async def update_budget(
        self,
        budget_id: UUID,
        *,
        monthly_limit: Decimal | None,
        limit_set: bool,
        timezone: str | None,
        timezone_set: bool,
    ) -> BudgetResponse | None:
        values: dict[str, Any] = {}
        if limit_set:
            values["monthly_limit"] = monthly_limit
        if timezone_set:
            values["timezone"] = timezone
        row = await orm_one(
            self.connection,
            update(Budget)
            .where(Budget.id == budget_id)
            .values(**values)
            .returning(*fields(Budget)),
        )
        return _budget(row) if row else None

    async def delete_budget(self, budget_id: UUID) -> bool:
        return (
            await orm_one(
                self.connection, delete(Budget).where(Budget.id == budget_id).returning(Budget.id)
            )
            is not None
        )

    async def list_provider_keys(
        self, *, provider: str | None, page: int, page_size: int
    ) -> tuple[list[ProviderKeyResponse], int]:
        statement = select(
            ProviderKey.id,
            ProviderKey.provider,
            ProviderKey.alias,
            ProviderKey.created_by,
            ProviderKey.created_at,
            ProviderKey.deactivated_at,
        ).where(ProviderKey.provider == "gemini")
        if provider is not None:
            statement = statement.where(ProviderKey.provider == provider)
        rows, total = await orm_page(
            self.connection,
            statement.order_by(ProviderKey.created_at.desc(), ProviderKey.id.desc()),
            page=page,
            page_size=page_size,
            order=[("created_at", True), ("id", True)],
        )
        return [_provider_key(row) for row in rows], total

    async def create_provider_key(
        self, provider: str, alias: str, encrypted_secret: bytes, actor_id: UUID
    ) -> ProviderKeyResponse:
        row = await orm_one(
            self.connection,
            insert(ProviderKey)
            .values(
                provider=provider,
                alias=alias,
                encrypted_secret=encrypted_secret,
                created_by=actor_id,
            )
            .returning(
                ProviderKey.id,
                ProviderKey.provider,
                ProviderKey.alias,
                ProviderKey.created_by,
                ProviderKey.created_at,
                ProviderKey.deactivated_at,
            ),
        )
        if row is None:
            raise RuntimeError("provider key insert returned no row")
        return _provider_key(row)

    async def deactivate_provider_key(self, key_id: UUID) -> bool:
        return (
            await orm_one(
                self.connection,
                update(ProviderKey)
                .where(ProviderKey.id == key_id, ProviderKey.deactivated_at.is_(None))
                .values(deactivated_at=func.current_timestamp())
                .returning(ProviderKey.id),
            )
            is not None
        )

    async def list_pricing(
        self,
        *,
        provider: str | None,
        model: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ModelPricingResponse], int]:
        statement = select(*fields(ModelPrice)).where(ModelPrice.provider == "gemini")
        if provider is not None:
            statement = statement.where(ModelPrice.provider == provider)
        if model is not None:
            statement = statement.where(ModelPrice.model == model)
        rows, total = await orm_page(
            self.connection,
            statement.order_by(ModelPrice.effective_from.desc(), ModelPrice.id.desc()),
            page=page,
            page_size=page_size,
            order=[("effective_from", True), ("id", True)],
        )
        return [_pricing(row) for row in rows], total

    async def create_pricing(
        self,
        *,
        provider: str,
        model: str,
        input_price: Decimal,
        output_price: Decimal,
        effective_from: datetime,
        effective_to: datetime | None,
        actor_id: UUID,
    ) -> ModelPricingResponse:
        row = await orm_one(
            self.connection,
            insert(ModelPrice)
            .values(
                provider=provider,
                model=model,
                input_price_per_million=input_price,
                output_price_per_million=output_price,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_id,
            )
            .returning(*fields(ModelPrice)),
        )
        if row is None:
            raise RuntimeError("pricing insert returned no row")
        return _pricing(row)

    async def maintenance_status(self) -> dict[str, Any]:
        view_cursor = await self.connection.execute(
            """
            SELECT m.matviewname AS name, m.ispopulated AS is_populated,
                   CASE m.matviewname
                     WHEN 'organization_monthly_metrics' THEN
                       (SELECT max(refreshed_through) FROM organization_monthly_metrics)
                     WHEN 'user_monthly_metrics' THEN
                       (SELECT max(refreshed_through) FROM user_monthly_metrics)
                   END AS refreshed_through
            FROM pg_matviews m
            WHERE m.schemaname = 'public'
              AND m.matviewname IN (
                  'organization_monthly_metrics', 'user_monthly_metrics'
              )
            ORDER BY m.matviewname
            """
        )
        partition_cursor = await self.connection.execute(
            """
            SELECT child.relname AS name,
                   pg_get_expr(child.relpartbound, child.oid) AS range_expression
            FROM pg_inherits
            JOIN pg_class parent ON parent.oid = inhparent
            JOIN pg_class child ON child.oid = inhrelid
            WHERE parent.relname = 'runs'
            ORDER BY child.relname
            """
        )
        count_cursor = await self.connection.execute(
            """SELECT
                (SELECT count(*) FROM provider_keys WHERE deactivated_at IS NULL)
                    AS active_provider_key_count,
                (SELECT count(*) FROM deployment_context WHERE status = 'pending')
                    AS pending_deployment_count,
                (SELECT max(created_at) FROM audit_events
                 WHERE action = 'refresh' AND entity_type = 'materialized_views')
                    AS last_view_refresh_at,
                (SELECT max(created_at) FROM audit_events
                 WHERE action = 'create' AND entity_type = 'run_partitions')
                    AS last_partition_creation_at"""
        )
        counts = await count_cursor.fetchone()
        if counts is None:
            raise RuntimeError("maintenance counts returned no row")
        return {
            "materialized_views": list(await view_cursor.fetchall()),
            "run_partitions": list(await partition_cursor.fetchall()),
            **counts,
        }

    async def refresh_views(self, actor_id: UUID, request_id: str) -> datetime:
        cursor = await self.connection.execute(
            "SELECT admin_refresh_reporting_views(%s, %s) AS completed_at",
            (actor_id, request_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("view refresh function returned no row")
        return cast(datetime, row["completed_at"])

    async def create_next_partition(self, actor_id: UUID, request_id: str) -> tuple[str, bool]:
        cursor = await self.connection.execute(
            "SELECT * FROM admin_create_next_run_partition(%s, %s)",
            (actor_id, request_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("partition function returned no row")
        return row["partition_name"], row["already_existed"]

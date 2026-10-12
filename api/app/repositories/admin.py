"""Super Admin governance persistence."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from api.app.repositories.pagination import read_page
from api.app.schemas.admin import (
    AdminUserResponse,
    ModelPricingResponse,
    ProviderKeyResponse,
)
from api.app.schemas.budgets import BudgetResponse
from api.app.schemas.runs import RunResponse, RunStatus
from psycopg import AsyncConnection

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
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def set_audit_context(self, actor_id: UUID, request_id: str) -> None:
        await self.connection.execute(
            "SELECT set_config('app.user_id', %s, true), "
            "set_config('app.request_id', %s, true)",
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
        cursor = await self.connection.execute(
            """
            SELECT u.id, u.email, u.display_name, u.role, u.is_active,
                   count(pm.project_id)::integer AS project_count,
                   u.created_at, u.updated_at
            FROM users u
            LEFT JOIN project_members pm ON pm.user_id = u.id
            WHERE u.id = %s
            GROUP BY u.id
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
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
            await self.connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = CURRENT_TIMESTAMP,
                    revocation_reason = 'account_changed'
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
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
                (SELECT count(*) FROM deployments WHERE status = 'pending')
                    AS pending_approval_count,
                count(*) AS run_count,
                count(*) FILTER (WHERE status = 'completed') AS completed_run_count,
                count(*) FILTER (WHERE status = 'failed') AS failed_run_count,
                count(*) FILTER (WHERE status = 'blocked') AS blocked_run_count,
                COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0) AS total_spend
            FROM runs
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
            FROM runs
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
            FROM runs
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
            FROM runs r JOIN users u ON u.id = r.user_id
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
            where.append(
                "(p.key ILIKE %s ESCAPE E'\\\\' OR r.id::text ILIKE %s ESCAPE E'\\\\')"
            )
            pattern = f"%{escaped_search}%"
            parameters.extend((pattern, pattern))
        where_sql = " AND ".join(where)
        rows, total = await read_page(
            self.connection,
            count_query=f"""SELECT count(*) AS total
                FROM runs r
                JOIN prompts p ON p.id = r.prompt_id
                WHERE {where_sql}""",
            items_query=f"""
            SELECT {_RUN_COLUMNS}
            FROM runs r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN prompt_versions pv ON pv.id = r.version_id
            WHERE {where_sql}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s OFFSET %s
            """,
            parameters=parameters,
            page=page,
            page_size=page_size,
            order_by='created_at DESC, id DESC',
        )
        return [_run(row) for row in rows], total

    async def list_budgets(
        self, *, user_id: UUID | None, project_id: UUID | None, page: int, page_size: int
    ) -> tuple[list[BudgetResponse], int]:
        where = ["TRUE"]
        parameters: list[Any] = []
        if user_id is not None:
            where.append("user_id = %s")
            parameters.append(user_id)
        if project_id is not None:
            where.append("project_id = %s")
            parameters.append(project_id)
        where_sql = " AND ".join(where)
        count_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM budgets WHERE {where_sql}", tuple(parameters)
        )
        total = await count_cursor.fetchone()
        cursor = await self.connection.execute(
            f"""SELECT id, user_id, project_id, monthly_limit, timezone,
                       created_by, created_at, updated_at
                FROM budgets WHERE {where_sql}
                ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s""",
            (*parameters, page_size, (page - 1) * page_size),
        )
        if total is None:
            raise RuntimeError("budget count returned no row")
        return [_budget(row) for row in await cursor.fetchall()], int(total["total"])

    async def create_budget(
        self,
        *,
        user_id: UUID | None,
        project_id: UUID | None,
        monthly_limit: Decimal,
        timezone: str,
        actor_id: UUID,
    ) -> BudgetResponse:
        cursor = await self.connection.execute(
            """INSERT INTO budgets (
                   user_id, project_id, monthly_limit, timezone, created_by
               ) VALUES (%s, %s, %s, %s, %s)
               RETURNING id, user_id, project_id, monthly_limit, timezone,
                         created_by, created_at, updated_at""",
            (user_id, project_id, monthly_limit, timezone, actor_id),
        )
        row = await cursor.fetchone()
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
        cursor = await self.connection.execute(
            """UPDATE budgets SET
                   monthly_limit = CASE WHEN %s THEN %s ELSE monthly_limit END,
                   timezone = CASE WHEN %s THEN %s ELSE timezone END
               WHERE id = %s
               RETURNING id, user_id, project_id, monthly_limit, timezone,
                         created_by, created_at, updated_at""",
            (limit_set, monthly_limit, timezone_set, timezone, budget_id),
        )
        row = await cursor.fetchone()
        return _budget(row) if row else None

    async def delete_budget(self, budget_id: UUID) -> bool:
        cursor = await self.connection.execute(
            "DELETE FROM budgets WHERE id = %s RETURNING id", (budget_id,)
        )
        return await cursor.fetchone() is not None

    async def list_provider_keys(
        self, *, provider: str | None, page: int, page_size: int
    ) -> tuple[list[ProviderKeyResponse], int]:
        where = "TRUE" if provider is None else "provider = %s"
        parameters: tuple[Any, ...] = () if provider is None else (provider,)
        total_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM provider_keys WHERE {where}", parameters
        )
        total = await total_cursor.fetchone()
        cursor = await self.connection.execute(
            f"""SELECT id, provider, alias, created_by, created_at, deactivated_at
                FROM provider_keys WHERE {where}
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
            (*parameters, page_size, (page - 1) * page_size),
        )
        if total is None:
            raise RuntimeError("provider key count returned no row")
        return [_provider_key(row) for row in await cursor.fetchall()], int(total["total"])

    async def create_provider_key(
        self, provider: str, alias: str, encrypted_secret: bytes, actor_id: UUID
    ) -> ProviderKeyResponse:
        cursor = await self.connection.execute(
            """INSERT INTO provider_keys (provider, alias, encrypted_secret, created_by)
               VALUES (%s, %s, %s, %s)
               RETURNING id, provider, alias, created_by, created_at, deactivated_at""",
            (provider, alias, encrypted_secret, actor_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("provider key insert returned no row")
        return _provider_key(row)

    async def deactivate_provider_key(self, key_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """UPDATE provider_keys SET deactivated_at = CURRENT_TIMESTAMP
               WHERE id = %s AND deactivated_at IS NULL RETURNING id""",
            (key_id,),
        )
        return await cursor.fetchone() is not None

    async def list_pricing(
        self,
        *,
        provider: str | None,
        model: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ModelPricingResponse], int]:
        where = ["TRUE"]
        parameters: list[Any] = []
        if provider:
            where.append("provider = %s")
            parameters.append(provider)
        if model:
            where.append("model = %s")
            parameters.append(model)
        where_sql = " AND ".join(where)
        total_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM model_pricing WHERE {where_sql}",
            tuple(parameters),
        )
        total = await total_cursor.fetchone()
        cursor = await self.connection.execute(
            f"""SELECT id, provider, model, input_price_per_million,
                       output_price_per_million, effective_from, effective_to,
                       created_by, created_at
                FROM model_pricing WHERE {where_sql}
                ORDER BY effective_from DESC, id DESC LIMIT %s OFFSET %s""",
            (*parameters, page_size, (page - 1) * page_size),
        )
        if total is None:
            raise RuntimeError("pricing count returned no row")
        return [_pricing(row) for row in await cursor.fetchall()], int(total["total"])

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
        cursor = await self.connection.execute(
            """INSERT INTO model_pricing (
                   provider, model, input_price_per_million,
                   output_price_per_million, effective_from, effective_to, created_by
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, provider, model, input_price_per_million,
                         output_price_per_million, effective_from, effective_to,
                         created_by, created_at""",
            (
                provider,
                model,
                input_price,
                output_price,
                effective_from,
                effective_to,
                actor_id,
            ),
        )
        row = await cursor.fetchone()
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
                (SELECT count(*) FROM deployments WHERE status = 'pending')
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

    async def create_next_partition(
        self, actor_id: UUID, request_id: str
    ) -> tuple[str, bool]:
        cursor = await self.connection.execute(
            "SELECT * FROM admin_create_next_run_partition(%s, %s)",
            (actor_id, request_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("partition function returned no row")
        return row["partition_name"], row["already_existed"]

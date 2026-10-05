"""Run target resolution and immutable ledger persistence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from api.app.schemas.runs import RunResponse, RunStatus
from api.app.schemas.versions import ModelConfiguration
from api.app.security import UserRole
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

_RUN_COLUMNS = """
    r.id, r.user_id, r.project_id, r.prompt_id, p.key AS prompt_key,
    r.version_id, pv.version_number, r.status, r.provider, r.model,
    r.input_variables, r.output_text, r.prompt_tokens, r.completion_tokens,
    r.latency_ms, r.cost, r.error_code, r.created_at
"""

_RUN_SUMMARY_COLUMNS = """
    r.id, r.user_id, r.project_id, r.prompt_id, p.key AS prompt_key,
    r.version_id, pv.version_number, r.status, r.provider, r.model,
    r.input_variables, left(r.output_text, 2000) AS output_text,
    r.prompt_tokens, r.completion_tokens, r.latency_ms, r.cost,
    r.error_code, r.created_at
"""


@dataclass(frozen=True, slots=True)
class RunTarget:
    project_id: UUID
    prompt_id: UUID
    prompt_key: str
    version_id: UUID
    version_number: int
    template_body: str
    variables: list[str]
    model_configuration: ModelConfiguration


def _run_from_row(row: Mapping[str, Any]) -> RunResponse:
    return RunResponse(
        id=row["id"],
        user_id=row["user_id"],
        project_id=row["project_id"],
        prompt_id=row["prompt_id"],
        prompt_key=row["prompt_key"],
        version_id=row["version_id"],
        version_number=row["version_number"],
        status=row["status"],
        provider=row["provider"],
        model=row["model"],
        input_variables=row["input_variables"],
        output_text=row["output_text"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        latency_ms=row["latency_ms"],
        cost=row["cost"],
        error_code=row["error_code"],
        created_at=row["created_at"],
    )


class RunRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def get_target_scoped(
        self,
        version_id: UUID,
        user_id: UUID,
        role: UserRole,
    ) -> RunTarget | None:
        cursor = await self.connection.execute(
            """
            SELECT p.project_id, p.id AS prompt_id, p.key AS prompt_key,
                   pv.id AS version_id, pv.version_number, pv.template_body,
                   pv.variables, pv.model_config
            FROM prompt_versions pv
            JOIN prompts p ON p.id = pv.prompt_id
            WHERE pv.id = %s
              AND (
                  %s = 'admin'
                  OR EXISTS (
                      SELECT 1 FROM project_members pm
                      WHERE pm.project_id = p.project_id AND pm.user_id = %s
                  )
              )
            """,
            (version_id, role, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return RunTarget(
            project_id=row["project_id"],
            prompt_id=row["prompt_id"],
            prompt_key=row["prompt_key"],
            version_id=row["version_id"],
            version_number=row["version_number"],
            template_body=row["template_body"],
            variables=row["variables"],
            model_configuration=ModelConfiguration.model_validate(row["model_config"]),
        )

    async def lock_execution_access(self, version_id: UUID, user_id: UUID) -> bool:
        user_cursor = await self.connection.execute(
            """
            SELECT role
            FROM users
            WHERE id = %s AND is_active
            FOR SHARE
            """,
            (user_id,),
        )
        user = await user_cursor.fetchone()
        if user is None:
            return False
        if user["role"] == "admin":
            cursor = await self.connection.execute(
                """
                SELECT pv.id
                FROM prompt_versions pv
                JOIN prompts p ON p.id = pv.prompt_id
                WHERE pv.id = %s
                FOR KEY SHARE OF pv, p
                """,
                (version_id,),
            )
        else:
            cursor = await self.connection.execute(
                """
                SELECT pv.id
                FROM prompt_versions pv
                JOIN prompts p ON p.id = pv.prompt_id
                JOIN project_members pm
                  ON pm.project_id = p.project_id AND pm.user_id = %s
                WHERE pv.id = %s
                FOR KEY SHARE OF pv, p, pm
                """,
                (user_id, version_id),
            )
        return await cursor.fetchone() is not None

    async def record(
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
        config = target.model_configuration
        cursor = await self.connection.execute(
            """
            SELECT recorded.id
            FROM record_run(
                p_user_id => %s,
                p_project_id => %s,
                p_prompt_id => %s,
                p_version_id => %s,
                p_status => %s,
                p_provider => %s,
                p_model => %s,
                p_input_variables => %s::jsonb,
                p_output_text => %s,
                p_prompt_tokens => %s,
                p_completion_tokens => %s,
                p_latency_ms => %s,
                p_cost => %s,
                p_error_code => %s,
                p_request_id => %s,
                p_created_at => %s
            ) AS recorded
            """,
            (
                user_id,
                target.project_id,
                target.prompt_id,
                target.version_id,
                status,
                config.provider,
                config.model,
                Jsonb(input_variables),
                output_text,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                cost,
                error_code,
                request_id,
                created_at,
            ),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("run function returned no row")
        recorded = await self.get(row["id"], user_id, "admin")
        if recorded is None:
            raise RuntimeError("recorded run was not returned")
        return recorded

    async def get(
        self,
        run_id: UUID,
        user_id: UUID,
        role: UserRole,
    ) -> RunResponse | None:
        cursor = await self.connection.execute(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM runs r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN prompt_versions pv ON pv.id = r.version_id
            WHERE r.id = %s
              AND (
                  %s = 'admin'
                  OR r.user_id = %s
                  OR EXISTS (
                      SELECT 1 FROM project_members pm
                      WHERE pm.project_id = r.project_id AND pm.user_id = %s
                  )
              )
            ORDER BY r.created_at DESC
            LIMIT 1
            """,
            (run_id, role, user_id, user_id),
        )
        row = await cursor.fetchone()
        return _run_from_row(row) if row else None

    async def list_scoped(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        project_id: UUID | None,
        prompt_id: UUID | None,
        version_id: UUID | None,
        status: RunStatus | None,
        model: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RunResponse], int]:
        where = [
            """(%s = 'admin' OR r.user_id = %s OR EXISTS (
                SELECT 1 FROM project_members pm
                WHERE pm.project_id = r.project_id AND pm.user_id = %s
            ))"""
        ]
        parameters: list[Any] = [role, user_id, user_id]
        filters = (
            ("r.project_id = %s", project_id),
            ("r.prompt_id = %s", prompt_id),
            ("r.version_id = %s", version_id),
            ("r.status = %s", status),
            ("r.model = %s", model),
            ("r.created_at >= %s", created_from),
            ("r.created_at < %s", created_to),
        )
        for clause, value in filters:
            if value is not None:
                where.append(clause)
                parameters.append(value)
        where_sql = " AND ".join(where)
        count_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM runs r WHERE {where_sql}",
            tuple(parameters),
        )
        total_row = await count_cursor.fetchone()
        if total_row is None:
            raise RuntimeError("run count returned no row")
        cursor = await self.connection.execute(
            f"""
            SELECT {_RUN_SUMMARY_COLUMNS}
            FROM runs r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN prompt_versions pv ON pv.id = r.version_id
            WHERE {where_sql}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, page_size, (page - 1) * page_size),
        )
        return [_run_from_row(row) for row in await cursor.fetchall()], int(total_row["total"])

    async def personal_metrics(
        self,
        *,
        user_id: UUID,
        month_start: datetime,
        month_end: datetime,
    ) -> Mapping[str, Any]:
        cursor = await self.connection.execute(
            """
            SELECT
                (SELECT count(*) FROM project_members WHERE user_id = %s) AS project_count,
                (
                    SELECT count(*)
                    FROM prompts p
                    WHERE EXISTS (
                        SELECT 1 FROM project_members pm
                        WHERE pm.project_id = p.project_id AND pm.user_id = %s
                    )
                ) AS prompt_count,
                (
                    SELECT count(*) FROM deployments
                    WHERE requested_by = %s AND status = 'pending'
                ) AS pending_approval_count,
                count(*) FILTER (WHERE r.created_at >= %s AND r.created_at < %s) AS run_count,
                count(*) FILTER (
                    WHERE r.status = 'completed' AND r.created_at >= %s AND r.created_at < %s
                ) AS completed_run_count,
                count(*) FILTER (
                    WHERE r.status = 'failed' AND r.created_at >= %s AND r.created_at < %s
                ) AS failed_run_count,
                count(*) FILTER (
                    WHERE r.status = 'blocked' AND r.created_at >= %s AND r.created_at < %s
                ) AS blocked_run_count,
                COALESCE(sum(r.cost) FILTER (
                    WHERE r.status = 'completed' AND r.created_at >= %s AND r.created_at < %s
                ), 0) AS monthly_spend
            FROM runs r
            WHERE r.user_id = %s
            """,
            (
                user_id,
                user_id,
                user_id,
                month_start,
                month_end,
                month_start,
                month_end,
                month_start,
                month_end,
                month_start,
                month_end,
                month_start,
                month_end,
                user_id,
            ),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("dashboard metrics returned no row")
        return row

    async def personal_cost_trend(
        self,
        *,
        user_id: UUID,
        month_start: datetime,
        month_end: datetime,
        timezone: str,
    ) -> list[Mapping[str, Any]]:
        cursor = await self.connection.execute(
            """
            SELECT (created_at AT TIME ZONE %s)::date AS date,
                   sum(cost) AS cost,
                   count(*) AS run_count
            FROM runs
            WHERE user_id = %s
              AND status = 'completed'
              AND created_at >= %s
              AND created_at < %s
            GROUP BY 1
            ORDER BY date
            """,
            (timezone, user_id, month_start, month_end),
        )
        return list(await cursor.fetchall())

    async def recent_for_user(self, user_id: UUID, *, limit: int = 10) -> list[RunResponse]:
        cursor = await self.connection.execute(
            f"""
            SELECT {_RUN_SUMMARY_COLUMNS}
            FROM runs r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN prompt_versions pv ON pv.id = r.version_id
            WHERE r.user_id = %s
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [_run_from_row(row) for row in await cursor.fetchall()]

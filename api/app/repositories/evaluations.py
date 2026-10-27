"""Durable evaluation history and a separate ledger for Gemini assistance calls."""

from datetime import timedelta
from typing import Any
from uuid import UUID

from api.app.db.orm import ORMConnection
from api.app.schemas.evaluations import CaseResult, EvaluationSetup, VersionRanking
from psycopg.types.json import Jsonb


class EvaluationRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def expire(self, seconds: float) -> None:
        await self.connection.execute(
            """UPDATE prompt_evaluations SET status='interrupted',
                error='Evaluation interrupted. Review partial results and start again.',
                winner_version_id=NULL, updated_at=clock_timestamp()
                WHERE status IN ('queued','running') AND updated_at < clock_timestamp() - %s""",
            (timedelta(seconds=seconds),),
        )

    async def get(self, evaluation_id: UUID) -> dict[str, Any] | None:
        cursor = await self.connection.execute(
            "SELECT * FROM prompt_evaluations WHERE id=%s", (evaluation_id,)
        )
        row = await cursor.fetchone()
        if row is not None:
            usage = await self.connection.execute(
                """SELECT count(*)::int AS evaluator_calls,
                coalesce(sum(prompt_tokens),0)::bigint AS evaluator_prompt_tokens,
                coalesce(sum(completion_tokens),0)::bigint AS evaluator_completion_tokens,
                coalesce(sum(latency_ms),0)::bigint AS evaluator_latency_ms
                FROM evaluation_calls WHERE evaluation_id=%s""",
                (evaluation_id,),
            )
            row["usage"] = await usage.fetchone()
        return row

    async def history(self, prompt_id: UUID) -> list[dict[str, Any]]:
        cursor = await self.connection.execute(
            """SELECT id,status,created_at,recommendation,winner_version_id,error,
                jsonb_array_length(results) AS completed_cases,
                jsonb_array_length(configuration->'cases') *
                jsonb_array_length(configuration->'version_ids') AS total_cases
                FROM prompt_evaluations e WHERE prompt_id=%s AND NOT EXISTS (
                    SELECT 1 FROM release_validations r WHERE r.evaluation_id=e.id)
                ORDER BY created_at DESC LIMIT 30""",
            (prompt_id,),
        )
        return await cursor.fetchall()

    async def save_setup(self, prompt_id: UUID, actor_id: UUID, setup: EvaluationSetup) -> None:
        await self.connection.execute("SELECT id FROM prompts WHERE id=%s FOR UPDATE", (prompt_id,))
        await self.connection.execute(
            """INSERT INTO prompt_evaluation_setups(prompt_id,configuration,updated_by)
            VALUES(%s,%s,%s) ON CONFLICT(prompt_id) DO UPDATE SET
            configuration=EXCLUDED.configuration,updated_by=EXCLUDED.updated_by,
            updated_at=clock_timestamp()""",
            (prompt_id, Jsonb(setup.model_dump(mode="json")), actor_id),
        )

    async def setup(self, prompt_id: UUID) -> dict[str, Any] | None:
        cursor = await self.connection.execute(
            "SELECT configuration FROM prompt_evaluation_setups WHERE prompt_id=%s", (prompt_id,)
        )
        row = await cursor.fetchone()
        return row["configuration"] if row else None

    async def create(
        self,
        evaluation_id: UUID,
        prompt_id: UUID,
        actor_id: UUID,
        setup: EvaluationSetup,
        snapshots: list[dict[str, Any]],
        *,
        save_setup: bool = True,
    ) -> None:
        await self.connection.execute(
            """INSERT INTO prompt_evaluations
            (id,prompt_id,created_by,configuration,version_snapshots)
            VALUES(%s,%s,%s,%s,%s)""",
            (
                evaluation_id,
                prompt_id,
                actor_id,
                Jsonb(setup.model_dump(mode="json")),
                Jsonb(snapshots),
            ),
        )
        if save_setup:
            await self.save_setup(prompt_id, actor_id, setup)

    async def claim(self, evaluation_id: UUID) -> bool:
        cursor = await self.connection.execute(
            """UPDATE prompt_evaluations SET status='running',updated_at=clock_timestamp()
            WHERE id=%s AND status='queued' RETURNING id""",
            (evaluation_id,),
        )
        return await cursor.fetchone() is not None

    async def update(
        self,
        evaluation_id: UUID,
        results: list[CaseResult],
        *,
        status: str = "running",
        ranking: list[VersionRanking] | None = None,
        recommendation: str = "",
        winner: UUID | None = None,
        error: str | None = None,
    ) -> None:
        await self.connection.execute(
            """UPDATE prompt_evaluations SET results=%s,status=%s,ranking=%s,
            recommendation=%s,winner_version_id=%s,error=%s,updated_at=clock_timestamp()
            WHERE id=%s AND status IN ('queued','running')""",
            (
                Jsonb([r.model_dump(mode="json") for r in results]),
                status,
                Jsonb([r.model_dump(mode="json") for r in ranking or []]),
                recommendation,
                winner,
                error,
                evaluation_id,
            ),
        )

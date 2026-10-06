"""Redacted, filterable audit-event persistence."""

from datetime import datetime
from typing import Any
from uuid import UUID

from api.app.schemas.admin import AuditEventResponse
from psycopg import AsyncConnection

_SECRET_FIELDS = {"password", "password_hash", "secret", "encrypted_secret", "token", "token_hash"}


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _redact(item)
            for key, item in value.items()
            if key.lower() not in _SECRET_FIELDS
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AuditRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def list_events(
        self,
        *,
        actor_id: UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AuditEventResponse], int]:
        where = ["TRUE"]
        parameters: list[Any] = []
        for clause, value in (
            ("actor_user_id = %s", actor_id),
            ("action = %s", action),
            ("entity_type = %s", entity_type),
            ("entity_id = %s", entity_id),
            ("created_at >= %s", created_from),
            ("created_at < %s", created_to),
        ):
            if value is not None:
                where.append(clause)
                parameters.append(value)
        where_sql = " AND ".join(where)
        count_cursor = await self.connection.execute(
            f"SELECT count(*) AS total FROM audit_events WHERE {where_sql}",
            tuple(parameters),
        )
        total = await count_cursor.fetchone()
        cursor = await self.connection.execute(
            f"""SELECT id, actor_user_id, action, entity_type, entity_id,
                       before_data, after_data, request_id, created_at
                FROM audit_events WHERE {where_sql}
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
            (*parameters, page_size, (page - 1) * page_size),
        )
        if total is None:
            raise RuntimeError("audit count returned no row")
        items = []
        for row in await cursor.fetchall():
            safe = dict(row)
            safe["before_data"] = _redact(safe["before_data"])
            safe["after_data"] = _redact(safe["after_data"])
            items.append(AuditEventResponse.model_validate(safe))
        return items, int(total["total"])

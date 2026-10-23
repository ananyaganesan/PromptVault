"""Redacted, filterable audit-event persistence."""

from datetime import datetime
from uuid import UUID

from api.app.db.models import AuditEvent, fields
from api.app.db.orm import ORMConnection, orm_page
from api.app.schemas.admin import AuditEventResponse
from sqlalchemy import select

_SECRET_FIELDS = {"password", "password_hash", "secret", "encrypted_secret", "token", "token_hash"}


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _redact(item) for key, item in value.items() if key.lower() not in _SECRET_FIELDS
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AuditRepository:
    def __init__(self, connection: ORMConnection) -> None:
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
        statement = select(*fields(AuditEvent))
        for column, operator, value in [
            (AuditEvent.actor_user_id, "__eq__", actor_id),
            (AuditEvent.action, "__eq__", action),
            (AuditEvent.entity_type, "__eq__", entity_type),
            (AuditEvent.entity_id, "__eq__", entity_id),
            (AuditEvent.created_at, "__ge__", created_from),
            (AuditEvent.created_at, "__lt__", created_to),
        ]:
            if value is not None:
                statement = statement.where(getattr(column, operator)(value))
        rows, total = await orm_page(
            self.connection,
            statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()),
            page=page,
            page_size=page_size,
            order=[("created_at", True), ("id", True)],
        )
        items = []
        for row in rows:
            safe = dict(row)
            safe["before_data"] = _redact(safe["before_data"])
            safe["after_data"] = _redact(safe["after_data"])
            items.append(AuditEventResponse.model_validate(safe))
        return items, total

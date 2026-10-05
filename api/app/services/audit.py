"""Secure read-only audit query service."""

from datetime import datetime
from uuid import UUID

from api.app.repositories.audit import AuditRepository
from api.app.schemas.admin import AuditEventResponse
from api.app.schemas.common import Page
from api.app.services.time_filters import normalize_datetime_window


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

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
    ) -> Page[AuditEventResponse]:
        created_from, created_to = normalize_datetime_window(created_from, created_to)
        items, total = await self.repository.list_events(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, page=page, page_size=page_size, total=total)

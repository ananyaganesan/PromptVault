"""Provider credential lookup for execution without exposing secret metadata."""

from api.app.db.models import ProviderKey
from api.app.db.orm import ORMConnection, orm_one
from sqlalchemy import select


class ProviderKeyRepository:
    def __init__(self, connection: ORMConnection) -> None:
        self.connection = connection

    async def newest_active_secret(self, provider: str) -> bytes | None:
        row = await orm_one(
            self.connection,
            select(ProviderKey.encrypted_secret)
            .where(ProviderKey.provider == provider, ProviderKey.deactivated_at.is_(None))
            .order_by(ProviderKey.created_at.desc(), ProviderKey.id.desc())
            .limit(1),
        )
        return bytes(row["encrypted_secret"]) if row else None

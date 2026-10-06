"""Provider credential lookup for execution without exposing secret metadata."""

from typing import Any

from psycopg import AsyncConnection


class ProviderKeyRepository:
    def __init__(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        self.connection = connection

    async def newest_active_secret(self, provider: str) -> bytes | None:
        cursor = await self.connection.execute(
            """SELECT encrypted_secret
               FROM provider_keys
               WHERE provider = %s AND deactivated_at IS NULL
               ORDER BY created_at DESC, id DESC
               LIMIT 1""",
            (provider,),
        )
        row = await cursor.fetchone()
        return bytes(row["encrypted_secret"]) if row is not None else None

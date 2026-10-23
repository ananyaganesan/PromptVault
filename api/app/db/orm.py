"""SQLAlchemy ORM execution within the same transaction as database procedures."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import Result
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.sql import Executable


class Rows:
    """Small cursor interface retained for advanced PostgreSQL queries."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.rowcount = result.rowcount

    async def fetchone(self) -> dict[str, Any] | None:
        row = self.result.mappings().fetchone()
        return dict(row) if row is not None else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.result.mappings().all()]


class ORMConnection:
    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection
        self.session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="rollback_only"
        )

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        transaction = (
            self.connection.begin_nested()
            if self.connection.in_transaction()
            else self.connection.begin()
        )
        async with transaction:
            try:
                yield
            finally:
                await self.session.close()

    async def execute(self, query: Any, parameters: Any = None) -> Rows:
        """Raw SQL boundary for stored procedures, locks and analytical reports."""
        try:
            if not isinstance(query, str):
                query = query.as_string()
            if isinstance(parameters, Sequence) and not isinstance(parameters, (str, bytes)):
                parameters = tuple(parameters)
            return Rows(await self.connection.exec_driver_sql(query, parameters))
        except DBAPIError as error:
            if isinstance(error.orig, Exception):
                raise error.orig from error
            raise

    async def commit(self) -> None:
        await self.session.close()
        await self.connection.commit()

    async def rollback(self) -> None:
        await self.session.close()
        await self.connection.rollback()


async def execute_orm(connection: Any, statement: Executable) -> Result[Any]:
    """Execute a mapped statement, retaining existing PostgreSQL error semantics."""
    try:
        return await cast(ORMConnection, connection).session.execute(statement)
    except DBAPIError as error:
        if isinstance(error.orig, Exception):
            raise error.orig from error
        raise


async def orm_one(connection: Any, statement: Executable) -> dict[str, Any] | None:
    row = (await execute_orm(connection, statement)).mappings().first()
    return dict(row) if row is not None else None


async def orm_all(connection: Any, statement: Executable) -> list[dict[str, Any]]:
    return [dict(row) for row in (await execute_orm(connection, statement)).mappings().all()]


async def orm_page(
    connection: Any,
    statement: Any,
    *,
    page: int,
    page_size: int,
    order: list[tuple[str, bool]],
) -> tuple[list[dict[str, Any]], int]:
    """One-statement ORM count/page snapshot, including empty/out-of-range pages."""
    from sqlalchemy import func, select, true

    total = (
        select(func.count().label("total"))
        .select_from(statement.order_by(None).subquery())
        .cte("orm_total")
    )
    items = statement.limit(page_size).offset((page - 1) * page_size).cte("orm_items")
    combined = select(*items.c, total.c.total.label("_page_total")).select_from(
        total.outerjoin(items, true())
    )
    combined = combined.order_by(
        *[items.c[name].desc() if descending else items.c[name].asc() for name, descending in order]
    )
    rows = await orm_all(connection, combined)
    if not rows:
        raise RuntimeError("ORM page total returned no row")
    total_count = int(rows[0]["_page_total"])
    items = [
        {key: value for key, value in row.items() if key != "_page_total"}
        for row in rows
        if row["id"] is not None
    ]
    return items, total_count

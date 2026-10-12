"""Count and page reads sharing one PostgreSQL statement snapshot."""

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection


async def read_page(
    connection: AsyncConnection[dict[str, Any]],
    *,
    count_query: str,
    items_query: str,
    parameters: Sequence[Any],
    page: int,
    page_size: int,
    order_by: str,
) -> tuple[list[dict[str, Any]], int]:
    # Queries/order are repository-owned SQL; all caller inputs remain parameters.
    # LEFT JOIN retains the total for empty and out-of-range pages.
    cursor = await connection.execute(
        f"""
        WITH counted AS ({count_query}), page_rows AS ({items_query})
        SELECT page_rows.*, counted.total AS _page_total
        FROM counted LEFT JOIN page_rows ON TRUE
        ORDER BY {order_by}
        """,
        (*parameters, *parameters, page_size, (page - 1) * page_size),
    )
    rows = await cursor.fetchall()
    if not rows:
        raise RuntimeError("page count returned no row")
    total = int(rows[0]["_page_total"])
    return [row for row in rows if row["id"] is not None], total

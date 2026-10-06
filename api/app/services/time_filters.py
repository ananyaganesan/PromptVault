"""Shared validation for bounded timestamp query filters."""

from datetime import UTC, datetime

from api.app.errors import AppError


def normalize_datetime_window(
    created_from: datetime | None,
    created_to: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    for value in (created_from, created_to):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise AppError(400, "invalid_filter", "Query filter is invalid")

    normalized_from = created_from.astimezone(UTC) if created_from is not None else None
    normalized_to = created_to.astimezone(UTC) if created_to is not None else None
    if (
        normalized_from is not None
        and normalized_to is not None
        and normalized_from >= normalized_to
    ):
        raise AppError(400, "invalid_filter", "Query filter is invalid")
    return normalized_from, normalized_to

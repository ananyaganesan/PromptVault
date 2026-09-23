"""Query-string contract enforcement."""

from collections.abc import Callable

from api.app.errors import AppError
from fastapi import Request


def allow_query_parameters(*allowed: str) -> Callable[[Request], None]:
    allowed_names = frozenset(allowed)

    def validate(request: Request) -> None:
        unknown = sorted(set(request.query_params) - allowed_names)
        if unknown:
            raise AppError(
                400,
                "invalid_filter",
                "Query filter is invalid",
                field_errors={f"query.{name}": ["Unsupported query parameter"] for name in unknown},
            )

    return validate

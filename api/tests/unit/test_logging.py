import json
import logging
from collections.abc import Iterator

import pytest
from api.app.config import Settings
from api.app.logging_config import JsonFormatter
from api.app.main import create_app
from fastapi.testclient import TestClient


class NoopPool:
    async def open(self, *, wait: bool = True) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def logging_client(test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings, pool_factory=lambda _: NoopPool())
    with TestClient(app) as client:
        yield client


def test_json_formatter_emits_allowlisted_structured_fields() -> None:
    record = logging.LogRecord(
        name="promptvault.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_test"
    record.method = "GET"
    record.path = "/health"
    record.status_code = 200
    record.duration_ms = 1.25
    record.password = "must-not-appear"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "request_completed"
    assert payload["request_id"] == "req_test"
    assert payload["status_code"] == 200
    assert "password" not in payload


def test_request_log_contains_request_id_and_omits_query_string(
    logging_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="promptvault.request"):
        response = logging_client.get("/health?token=private-query-secret")

    records = [record for record in caplog.records if record.name == "promptvault.request"]
    assert len(records) == 1
    record = records[0]
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0
    assert "private-query-secret" not in record.getMessage()

import pytest
from api.app.config import Settings
from api.app.main import create_app
from fastapi.testclient import TestClient


class FakePool:
    def __init__(self, fail_open: bool = False) -> None:
        self.fail_open = fail_open
        self.opened = False
        self.closed = False

    async def open(self, *, wait: bool = True) -> None:
        if self.fail_open:
            raise ConnectionError("database unavailable")
        self.opened = True

    async def close(self) -> None:
        self.closed = True


def test_lifespan_opens_and_closes_one_pool(test_settings: Settings) -> None:
    pool = FakePool()
    app = create_app(test_settings, pool_factory=lambda _: pool)

    with TestClient(app):
        assert pool.opened is True
        assert app.state.db_pool is pool

    assert pool.closed is True


def test_pool_open_failure_aborts_startup(test_settings: Settings) -> None:
    pool = FakePool(fail_open=True)
    app = create_app(test_settings, pool_factory=lambda _: pool)

    with pytest.raises(ConnectionError, match="database unavailable"), TestClient(app):
        pass

    assert pool.closed is False

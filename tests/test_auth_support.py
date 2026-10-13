from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth_support import create_verified_test_user


def test_create_verified_test_user_refuses_non_test_database() -> None:
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        database_url="postgresql://promptvault:promptvault@localhost:5432/promptvault"
    )

    with pytest.raises(RuntimeError, match="database name must end in _test"):
        create_verified_test_user(TestClient(app), "unsafe")

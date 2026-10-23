"""Gemini simulation for tests only; never registered with the application."""

import asyncio
import re
from uuid import uuid4

import psycopg
import pytest

from api.app.config import Settings
from api.app.providers.base import ProviderRequest, ProviderResult
from api.app.providers.errors import ProviderExecutionError, ProviderTimeoutError
from api.app.providers.factory import get_provider
from api.app.security import encrypt_provider_secret

TEST_CREDENTIAL = "isolated-gemini-test-key"


def seed_gemini_test_credential(settings: Settings) -> None:
    with psycopg.connect(settings.database_url) as c:
        if not c.info.dbname.endswith("_test"):
            raise RuntimeError(
                "Gemini test fixtures require an isolated _test database"
            )
        c.execute(
            """INSERT INTO provider_keys(provider,alias,encrypted_secret,created_by)
            SELECT 'gemini',%s,%s,id FROM users
            WHERE role='admin' AND is_active ORDER BY created_at LIMIT 1
            ON CONFLICT DO NOTHING""",
            (
                "isolated-test-" + uuid4().hex,
                encrypt_provider_secret(
                    TEST_CREDENTIAL, settings.resolved_provider_encryption_key
                ),
            ),
        )


class SimulatedGemini:
    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if "[test-timeout]" in request.prompt:
            raise ProviderTimeoutError("simulated Gemini timeout")
        if "[test-error]" in request.prompt:
            raise ProviderExecutionError("simulated Gemini failure")
        if "[test-crash]" in request.prompt:
            raise RuntimeError("simulated unexpected Gemini failure")
        await asyncio.sleep(0.2)
        output = f"Simulated Gemini response: {request.prompt}"
        tokens = lambda value: len(re.findall(r"\w+|[^\w\s]", value))
        return ProviderResult(
            output, tokens(request.prompt), max(1, tokens(request.prompt) + 3), 25
        )


@pytest.fixture(autouse=True)
def simulate_fixture_gemini(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    if "run_client" in request.fixturenames:
        seed_gemini_test_credential(
            request.getfixturevalue("run_client").app.state.settings
        )

    def provider(name: str, *, credential: str | None = None, **kwargs):
        if name == "gemini" and credential == TEST_CREDENTIAL:
            return SimulatedGemini()
        return get_provider(name, credential=credential, **kwargs)

    monkeypatch.setattr("api.app.services.playground.get_provider", provider)

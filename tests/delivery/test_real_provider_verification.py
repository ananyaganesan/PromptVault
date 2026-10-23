"""Verifier guardrails and reconciliation; every provider call here is simulated."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.support import admin_headers

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify-real-providers.py"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--execute"],
        ["--provider", "deepseek"],
        ["--api-url", "https://example.com/api/v1"],
    ],
)
def test_verification_rejects_unsafe_configuration_before_connecting(
    arguments: list[str],
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            "postgresql://localhost/isolated_test",
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


@pytest.mark.database
def test_real_verifier_reconciles_runs_and_replays_with_simulated_http(
    api_client: TestClient,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location("real_verifier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    admin = admin_headers(api_client)
    for provider in ["gemini"]:
        assert (
            api_client.post(
                "/api/v1/admin/provider-keys",
                headers=admin,
                json={
                    "provider": provider,
                    "alias": "simulated-verifier",
                    "secret": "test-only-secret",
                },
            ).status_code
            == 201
        )

    calls = []

    def provider_response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            data = {
                "candidates": [
                    {"content": {"parts": [{"text": "Simulated connection"}]}}
                ],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
            }
        else:
            assert request.url.host in {"openrouter.ai", "api.groq.com"}
            data = {
                "choices": [{"message": {"content": "Simulated connection"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            }
        return httpx.Response(200, json=data)

    def local_response(request: httpx.Request) -> httpx.Response:
        assert request.url.host in {"localhost", "127.0.0.1"}
        response = api_client.request(
            request.method,
            request.url.path,
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=dict(response.headers),
        )

    client, async_client = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(local_response), **kwargs
        ),
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            transport=httpx.MockTransport(provider_response), **kwargs
        ),
    )
    monkeypatch.setenv("PV_VERIFY_EMAIL", "admin@promptvault.dev")
    monkeypatch.setenv("PV_VERIFY_PASSWORD", "AdminDemo2026!")
    output = tmp_path / "simulated-verifier.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--database-url",
            database_url,
            "--execute",
            "--free-tier-accounts-confirmed",
            "--output",
            str(output),
        ],
    )
    assert module.main() == 0
    assert len(calls) == 1  # Replays must never issue a second provider request.
    report = json.loads(output.read_text())
    assert {row["provider"] for row in report["providers"]} == {
        "gemini",
    }
    assert all(
        row["persisted"] and row["idempotent_replay"] for row in report["providers"]
    )
    assert all(row["application_cost"] == "0.000000" for row in report["providers"])
    assert "test-only-secret" not in output.read_text()

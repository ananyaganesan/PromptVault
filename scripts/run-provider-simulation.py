#!/usr/bin/env python3
"""Local A1 browser acceptance with simulated provider HTTP; never makes LLM calls."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.app.config import Settings
from api.app.main import create_app


def simulated_response(request: httpx.Request) -> httpx.Response:
    hosts = {
        "generativelanguage.googleapis.com": "gemini",
        "openrouter.ai": "openrouter",
        "api.groq.com": "groq",
    }
    provider = hosts.get(request.url.host)
    if provider is None or request.method != "POST":
        raise RuntimeError("Simulation denied an unexpected external request")
    body = json.loads(request.content)
    if "quota-test" in json.dumps(body):
        return httpx.Response(429, json={"error": "simulated quota rejection"})
    output = f"Simulated {provider} output for local acceptance"
    if provider == "gemini":
        data = {
            "candidates": [{"content": {"parts": [{"text": output}]}}],
            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
        }
    else:
        data = {
            "choices": [{"message": {"content": output}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
    return httpx.Response(200, json=data)


def main() -> None:
    database_url = os.environ["E2E_DATABASE_URL"]
    if not urlsplit(database_url).path.endswith("_test"):
        raise SystemExit(
            "Provider simulation requires a disposable database ending in _test"
        )
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(simulated_response)
    # Route every outbound async HTTP request through the simulator: no live calls.
    httpx.AsyncClient = lambda **kwargs: original_client(transport=transport, **kwargs)
    settings = Settings(
        environment="test",
        database_url=database_url,
        secret_key="simulation-only-secret-at-least-32-characters",
        cors_origins="http://127.0.0.1:5177",
        auth_rate_limit_requests=10000,
        password_reset_rate_limit_requests=10000,
        _env_file=None,
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8004)


if __name__ == "__main__":
    main()

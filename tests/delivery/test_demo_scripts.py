"""Delivery CLIs execute real HTTP and PostgreSQL workflows."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_version_race_demo_creates_contiguous_versions(database_url: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "version-race-demo.py"),
            "--database-url",
            database_url,
            "--workers",
            "4",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Concurrent version saves: 4" in result.stdout
    assert "Assigned versions: 2, 3, 4, 5" in result.stdout


@pytest.mark.database
def test_approval_race_demo_has_one_winner(database_url: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "approval-race-demo.py"),
            "--database-url",
            database_url,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Successful decisions: 1" in result.stdout
    assert "Conflicting decisions: 1" in result.stdout


@pytest.mark.database
def test_showcase_runner_executes_every_query_file(database_url: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "run-showcase.py"),
            "--database-url",
            database_url,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for filename in (
        "cost-analytics.sql",
        "deployment-history.sql",
        "maintenance-procedure.sql",
        "query-plans.sql",
        "version-lineage.sql",
    ):
        assert f"{filename}:" in result.stdout


def test_serve_client_sends_runtime_token_and_prints_prompt() -> None:
    observed: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            observed["path"] = self.path
            observed["authorization"] = self.headers.get("Authorization", "")
            payload = json.dumps(
                {
                    "project_id": "33333333-3333-4333-8333-333333333333",
                    "prompt_key": "support-reply",
                    "environment": "prod",
                    "version": {
                        "id": "55555555-5555-4555-8555-555555555555",
                        "version_number": 1,
                    },
                    "template_body": "Hello {{name}}",
                    "variables": ["name"],
                    "model_config": {"provider": "mock", "model": "deterministic-v1"},
                    "activated_at": "2026-09-27T00:00:00Z",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "scripts" / "serve-client.py"),
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--token",
                "pv_live_example_secret",
                "--key",
                "support-reply",
                "--env",
                "prod",
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"]["version_number"] == 1
    assert observed == {
        "path": "/serve/v1/prompts/support-reply?env=prod",
        "authorization": "Bearer pv_live_example_secret",
    }

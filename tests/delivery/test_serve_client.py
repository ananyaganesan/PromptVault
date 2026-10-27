"""The local Serve client sends project-scoped runtime credentials."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("token_key", [None, "DEMO_RUNTIME_TOKEN", "PROMPTVAULT_SERVE_TOKEN"])
def test_serve_client_sends_runtime_token_and_prints_prompt(tmp_path: Path, token_key: str | None) -> None:
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
                    "model_config": {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
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

    if token_key:
        token_file = tmp_path / "runtime.env"
        token_file.write_text(f"{token_key}=pv_live_example_secret\n")
        token_args = ["--token-file", str(token_file)]
    else:
        token_args = ["--token", "pv_live_example_secret"]

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
                *token_args,
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

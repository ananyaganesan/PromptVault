#!/usr/bin/env python3
"""Verify a committed PromptVault revision in an isolated clean checkout."""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = REPOSITORY_ROOT / "evidence" / "release" / "latest.txt"

REDACTIONS = (
    (re.compile(r"\bpv_live_[A-Za-z0-9_-]+"), "[REDACTED_RUNTIME_TOKEN]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(r"(postgres(?:ql)?://[^:\s/]+:)[^@\s/]+(@)", re.IGNORECASE),
        r"\1[REDACTED]\2",
    ),
    (
        re.compile(
            r"((?:access_)?token|password|secret|authorization)([\"']?\s*[:=]\s*[\"']?)"
            r"([^\"'\s,}]+)",
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED]",
    ),
)


def redact(value: str) -> str:
    redacted = value
    for pattern, replacement in REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def normalize_evidence(value: str) -> str:
    """Remove transport whitespace without changing transcript line structure."""
    return "\n".join(line.rstrip() for line in value.split("\n"))


def repository_is_clean(repository: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return not result.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, default=DEFAULT_EVIDENCE)
    return parser


def available_port() -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return str(listener.getsockname()[1])


def verification_environment(commit: str) -> dict[str, str]:
    environment = os.environ.copy()
    api_port = available_port()
    web_port = available_port()
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": f"promptvault-verify-{commit[:8].lower()}",
            "ENVIRONMENT": "development",
            "POSTGRES_DB": "promptvault",
            "POSTGRES_USER": "promptvault",
            "POSTGRES_PASSWORD": "promptvault",
            "POSTGRES_PORT": available_port(),
            "API_PORT": api_port,
            "WEB_PORT": web_port,
            "VITE_API_URL": f"http://localhost:{api_port}",
            "CORS_ORIGINS": f"http://localhost:{web_port}",
            "SECRET_KEY": "change-me",
            "PROVIDER_ENCRYPTION_KEY": "change-me-provider-encryption-key",
        }
    )
    environment.pop("DATABASE_URL", None)
    environment.pop("TEST_DATABASE_URL", None)
    return environment


class Verification:
    def __init__(
        self,
        checkout: Path,
        evidence_file: Path,
        environment: dict[str, str],
    ) -> None:
        self.checkout = checkout
        self.evidence_file = evidence_file
        self.environment = environment
        self.lines: list[str] = []

    def record(self, value: str) -> None:
        safe_value = normalize_evidence(redact(value))
        print(safe_value)
        self.lines.append(safe_value)

    def command(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        display = " ".join(arguments)
        self.record(f"\n$ {display}")
        result = subprocess.run(
            arguments,
            cwd=self.checkout,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            self.record(result.stdout.rstrip())
        if result.stderr.strip():
            self.record(result.stderr.rstrip())
        if result.returncode:
            raise RuntimeError(f"command failed with exit code {result.returncode}: {display}")
        return result

    def probe(self, url: str) -> None:
        self.record(f"\nHTTP GET {url}")
        try:
            with urlopen(url, timeout=10) as response:
                status = response.status
                body = response.read(500).decode(errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"HTTP probe failed for {url}: {exc}") from exc
        self.record(f"HTTP {status} {body}")
        if status != 200:
            raise RuntimeError(f"expected HTTP 200, received {status}")

    def login_probe(self, api_url: str) -> None:
        url = f"{api_url}/api/v1/auth/login"
        payload = json.dumps(
            {"email": "user@promptvault.dev", "password": "UserDemo2026!"}
        ).encode()
        request = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self.record(f"\nHTTP POST {url} (seeded User credentials redacted)")
        try:
            with urlopen(request, timeout=10) as response:
                status = response.status
                body = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"login probe failed: {exc}") from exc
        if status != 200 or body.get("user", {}).get("role") != "user":
            raise RuntimeError("login probe returned an unexpected response")
        self.record("HTTP 200 seeded User login succeeded; access token redacted")

    def write(self, result: str) -> None:
        self.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_file.write_text("\n".join(self.lines) + f"\n\nRESULT: {result}\n")


def ensure_test_database(verification: Verification) -> None:
    result = verification.command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "promptvault",
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = 'promptvault_test'",
        ]
    )
    if result.stdout.strip() != "1":
        verification.command(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "createdb",
                "-U",
                "promptvault",
                "promptvault_test",
            ]
        )


def add_clean_checkout(commit: str, checkout: Path) -> None:
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(checkout), commit],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def remove_clean_checkout(checkout: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(checkout)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def main() -> int:
    args = build_parser().parse_args()
    if not repository_is_clean(REPOSITORY_ROOT):
        print(
            "Release verification refused: commit or remove every working-tree change first.",
            file=sys.stderr,
        )
        return 2

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    temporary_root = Path(tempfile.mkdtemp(prefix="promptvault-release-"))
    checkout = temporary_root / "checkout"
    verification: Verification | None = None
    result = "FAILED"
    try:
        add_clean_checkout(commit, checkout)
        environment = verification_environment(commit)
        verification = Verification(
            checkout,
            args.evidence_file.resolve(),
            environment,
        )
        verification.record("PromptVault release verification")
        verification.record(f"UTC started: {datetime.now(UTC).isoformat()}")
        verification.record(f"Commit: {commit}")
        verification.record("Source: clean detached Git worktree")
        verification.record(f"Compose project: {environment['COMPOSE_PROJECT_NAME']}")
        verification.command(["docker", "compose", "config", "--quiet"])
        verification.command(["docker", "compose", "build", "--pull"])
        verification.command(["docker", "compose", "up", "-d", "--wait"])
        ensure_test_database(verification)
        verification.command(
            ["docker", "compose", "--profile", "verification", "run", "--rm", "verify"]
        )
        api_url = f"http://127.0.0.1:{environment['API_PORT']}"
        verification.probe(f"{api_url}/health")
        verification.probe(f"{api_url}/ready")
        verification.probe(f"http://127.0.0.1:{environment['WEB_PORT']}/")
        verification.login_probe(api_url)
        verification.command(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "migrate",
                "python",
                "scripts/version-race-demo.py",
                "--workers",
                "4",
            ]
        )
        verification.command(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "migrate",
                "python",
                "scripts/approval-race-demo.py",
            ]
        )
        verification.command(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "migrate",
                "python",
                "scripts/simulate-traffic.py",
                "--runs",
                "2000",
            ]
        )
        verification.command(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "migrate",
                "python",
                "scripts/run-showcase.py",
                "--max-rows",
                "2",
            ]
        )
        result = "PASSED"
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if verification is not None:
            verification.record(f"\nVERIFICATION FAILED: {exc}")
        else:
            print(f"Release verification failed: {redact(str(exc))}", file=sys.stderr)
    finally:
        if verification is not None:
            try:
                verification.command(
                    ["docker", "compose", "down", "-v", "--remove-orphans"]
                )
            except RuntimeError as exc:
                verification.record(f"Cleanup failed: {exc}")
                result = "FAILED"
        if checkout.exists():
            try:
                remove_clean_checkout(checkout)
            except subprocess.SubprocessError as exc:
                if verification is not None:
                    verification.record(f"Worktree cleanup failed: {exc}")
                result = "FAILED"
        shutil.rmtree(temporary_root, ignore_errors=True)
        if verification is not None:
            verification.record(f"\nUTC completed: {datetime.now(UTC).isoformat()}")
            verification.write(result)
    return 0 if result == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

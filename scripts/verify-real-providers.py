"""Verify configured real providers through the local API and disposable database."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app.providers.catalog import MODELS
from api.app.providers.policy import EXTERNAL_PROVIDERS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--database-url")
    parser.add_argument(
        "--provider", choices=sorted(EXTERNAL_PROVIDERS), action="append"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send one real request per ready provider",
    )
    parser.add_argument(
        "--local-development-database",
        action="store_true",
        help="Use the persistent local promptvault database on port 5432",
    )
    parser.add_argument(
        "--free-tier-accounts-confirmed",
        action="store_true",
        help="Keys belong to free-tier accounts; required for actual calls",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evidence/a1/real-provider-check.json"
    )
    args = parser.parse_args()
    if not args.database_url and args.local_development_database:
        args.database_url = os.environ.get("DATABASE_URL") or dotenv_values(
            ROOT / ".env"
        ).get("DATABASE_URL")
    if not args.database_url:
        parser.error(
            "Set --database-url or select the configured --local-development-database"
        )
    if urlsplit(args.api_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Verification must target a loopback local API")
    database_parts = urlsplit(args.database_url)
    if args.local_development_database:
        if (
            database_parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            or (database_parts.port or 5432) != 5432
            or database_parts.path != "/promptvault"
        ):
            parser.error("Development verification requires localhost:5432/promptvault")
    elif not database_parts.path.endswith("_test"):
        parser.error(
            "Verification requires a disposable _test database or explicit local development mode"
        )
    if args.execute and not args.free_tier_accounts_confirmed:
        parser.error("Confirm free-tier account credentials before executing")
    providers = sorted(set(args.provider or EXTERNAL_PROVIDERS))
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "execution_requested": args.execute,
        "free_tier_accounts_confirmed": args.free_tier_accounts_confirmed,
        "providers": [],
    }

    def save() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8"
        )

    with psycopg.connect(args.database_url, row_factory=dict_row) as database:
        database.execute("SET TRANSACTION READ ONLY")
        actual_database = database.execute(
            "SELECT current_database() AS name"
        ).fetchone()["name"]
        if actual_database != database_parts.path.lstrip("/"):
            parser.error("Connected database does not match the selected database")
        with httpx.Client(
            base_url=args.api_url.rstrip("/") + "/", timeout=45
        ) as client:
            login = client.post(
                "auth/login",
                json={
                    "email": os.environ.get("PV_VERIFY_EMAIL", "admin@promptvault.dev"),
                    "password": os.environ.get("PV_VERIFY_PASSWORD", "AdminDemo2026!"),
                },
            )
            if login.status_code != 200:
                print(
                    f"Local sign-in failed (HTTP {login.status_code}); no provider calls sent."
                )
                return 2
            session = login.json()
            # Prove API/SQL reconciliation targets the same authenticated fixture.
            if not database.execute(
                "SELECT id FROM users WHERE id=%s AND email=%s",
                (session["user"]["id"], session["user"]["email"]),
            ).fetchone():
                print(
                    "Local API account does not match the evidence database; no calls sent."
                )
                return 2
            client.headers["Authorization"] = f"Bearer {session['access_token']}"
            try:
                discovery = client.get("providers/models")
                discovery.raise_for_status()
                catalog = discovery.json()["items"]
                if {item["provider"] for item in catalog} != EXTERNAL_PROVIDERS:
                    raise RuntimeError(
                        "Local discovery violates the fixed provider scope"
                    )
                for provider in providers:
                    item = next(row for row in catalog if row["provider"] == provider)
                    model = next(
                        model for model in MODELS if model.provider == provider
                    )
                    available = next(
                        (row for row in item["models"] if row["id"] == model.id), None
                    )
                    result = {
                        "provider": provider,
                        "model": model.id,
                        "credential_available": item["credential_available"],
                        "status": "not_executed",
                    }
                    report["providers"].append(result)
                    if (
                        not item["credential_available"]
                        or not available
                        or not available["available"]
                    ):
                        result["status"] = "blocked_configuration"
                        continue
                    if not args.execute:
                        result["status"] = "ready_not_executed"
                        continue
                    suffix = uuid4().hex
                    project_response = client.post(
                        "projects",
                        json={
                            "name": f"Real {provider} verification",
                            "key": f"real-{provider}-{suffix}",
                        },
                    )
                    project_response.raise_for_status()
                    prompt_response = client.post(
                        f"projects/{project_response.json()['id']}/prompts",
                        json={
                            "name": "Real provider connection check",
                            "key": "connection-check",
                            "template_body": "Reply with one short sentence confirming this connection.",
                            "model_config": {
                                "provider": provider,
                                "model": model.id,
                                "temperature": 0,
                                "max_output_tokens": 512,
                            },
                            "commit_message": "Real free-tier provider acceptance",
                        },
                    )
                    prompt_response.raise_for_status()
                    version = prompt_response.json()["latest_version"]["id"]
                    payload = {"version_id": version, "variables": {}}
                    headers = {"Idempotency-Key": f"real-verification-{suffix}"}
                    result.update(status="request_pending", version_id=version)
                    save()
                    execution = client.post("runs", json=payload, headers=headers)
                    if execution.status_code != 201:
                        result.update(
                            status="failed",
                            http_status=execution.status_code,
                            error_code=execution.json().get("code", "unknown"),
                        )
                        save()
                        continue
                    run = execution.json()
                    persisted = database.execute(
                        """
                        SELECT provider,model,status,output_text,prompt_tokens,completion_tokens,
                               latency_ms,cost FROM run_context WHERE id=%s AND version_id=%s
                    """,
                        (run["id"], version),
                    ).fetchone()
                    expected = (
                        {key: run[key] for key in persisted if key != "cost"}
                        if persisted
                        else None
                    )
                    if not persisted or Decimal(run["cost"]) != persisted["cost"]:
                        raise RuntimeError("Persisted cost does not match the API")
                    if any(persisted[key] != expected[key] for key in expected):
                        raise RuntimeError("Persisted result does not match the API")
                    if (
                        run["status"] != "completed"
                        or not run["output_text"].strip()
                        or Decimal(run["cost"]) != 0
                    ):
                        raise RuntimeError(
                            "Real execution did not complete at zero application cost"
                        )
                    detail = client.get(f"runs/{run['id']}")
                    detail.raise_for_status()
                    replay = client.post("runs", json=payload, headers=headers)
                    replay.raise_for_status()
                    if detail.json() != run or replay.json()["id"] != run["id"]:
                        raise RuntimeError("Detail/replay reconciliation failed")
                    result.update(
                        status="verified_real",
                        run_id=run["id"],
                        version_id=version,
                        prompt_tokens=run["prompt_tokens"],
                        completion_tokens=run["completion_tokens"],
                        latency_ms=run["latency_ms"],
                        application_cost=run["cost"],
                        output_sha256=sha256(run["output_text"].encode()).hexdigest(),
                        output_characters=len(run["output_text"]),
                        persisted=True,
                        idempotent_replay=True,
                    )
                    save()
            finally:
                client.post("auth/logout")
    save()
    for result in report["providers"]:
        print(f"{result['provider']}: {result['status']}")
    return (
        0 if all(row["status"] == "verified_real" for row in report["providers"]) else 2
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        httpx.HTTPError,
        psycopg.Error,
        RuntimeError,
        KeyError,
        ValueError,
    ) as error:
        # Never echo HTTP requests/headers, credentials, SQL parameters or response bodies.
        print(
            f"Verification stopped safely ({type(error).__name__}); no automatic retries.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

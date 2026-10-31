#!/usr/bin/env python3
"""Mirror committed local PromptVault changes to its Supabase database."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict

from api.app.db.migrations import MigrationError
from api.app.db.supabase_sync import SyncRefused, load_state, reconcile, save_state

PROJECT_REF = "ehnufhcdgxllubnpjfuc"
PRIVATE = ROOT / "secrets/supabase-sync"
STATE = PRIVATE / "state.json"
LABEL = "com.promptvault.supabase-sync"
AGENT = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")


def connections() -> tuple[str, str]:
    source = dotenv_values(ROOT / ".env").get("DATABASE_URL", "")
    target = dotenv_values(ROOT / "secrets/supabase.env").get(
        "SUPABASE_DATABASE_URL", ""
    )
    if not source or not target or "[YOUR-PASSWORD]" in target:
        raise SyncRefused(
            "Set SUPABASE_DATABASE_URL in secrets/supabase.env with the real password"
        )
    try:
        local, remote = conninfo_to_dict(source), conninfo_to_dict(target)
    except psycopg.Error:
        raise SyncRefused("The saved PostgreSQL URI is invalid") from None
    if (
        local.get("host") not in {"localhost", "127.0.0.1", "::1"}
        or local.get("port", "5432") != "5432"
        or local.get("dbname") != "promptvault"
    ):
        raise SyncRefused("The source must remain localhost:5432/promptvault")
    host = remote.get("host", "")
    scoped = host == f"db.{PROJECT_REF}.supabase.co" or (
        host.endswith(".pooler.supabase.com")
        and remote.get("user") == f"postgres.{PROJECT_REF}"
    )
    if (
        not scoped
        or remote.get("dbname") != "postgres"
        or remote.get("port", "5432") != "5432"
    ):
        raise SyncRefused(
            "Use the PromptVault project's direct or Session pooler URI on port 5432"
        )
    if remote.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise SyncRefused("The Supabase URI must require SSL")
    return source, target


def run_once() -> dict:
    source_url, target_url = connections()
    with (
        psycopg.connect(source_url, connect_timeout=10, autocommit=True) as source,
        psycopg.connect(
            target_url,
            connect_timeout=10,
            autocommit=True,
            prepare_threshold=None,
            application_name="promptvault_local_sync",
        ) as target,
    ):
        return reconcile(
            source,
            target,
            state_path=STATE,
            baseline_path=ROOT / "evidence/database/supabase-migration.json",
            migrations_directory=ROOT / "db/migrations",
        )


def install_agent(interval: int) -> None:
    if sys.platform != "darwin":
        raise SyncRefused("Automatic installation currently supports macOS launchd")
    # Run and verify one real synchronization before enabling the repeating job.
    result = run_once()
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [
            str(ROOT / ".venv/bin/python"),
            str(Path(__file__).resolve()),
        ],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "StartInterval": interval,
        "ProcessType": "Background",
        "StandardOutPath": str(PRIVATE / "sync.log"),
        "StandardErrorPath": str(PRIVATE / "sync-error.log"),
    }
    AGENT.write_bytes(plistlib.dumps(config))
    AGENT.chmod(0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain + "/" + LABEL], capture_output=True, check=False
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(AGENT)], capture_output=True, check=True
    )
    print(
        json.dumps(
            {"automatic_sync_installed": True, "interval_seconds": interval, **result}
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-agent", action="store_true")
    group.add_argument("--stop-agent", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    if args.interval < 5:
        parser.error("The interval must be at least five seconds")
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    if args.status:
        state = load_state(STATE)
        print(
            json.dumps(
                {
                    key: value
                    for key, value in state.items()
                    if key not in {"manifest", "pending_manifest"}
                },
                indent=2,
            )
        )
        return 0
    if args.stop_agent:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
            capture_output=True,
            check=True,
        )
        # Prevent the job from being reloaded on the next login.
        if AGENT.exists():
            AGENT.rename(AGENT.with_suffix(".plist.disabled"))
        print("Automatic Supabase synchronization stopped.")
        return 0
    with (PRIVATE / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            if args.install_agent:
                install_agent(args.interval)
            else:
                print(json.dumps(run_once()))
            return 0
        except (
            SyncRefused,
            MigrationError,
            psycopg.Error,
            OSError,
            subprocess.SubprocessError,
            ValueError,
        ) as error:
            # Driver diagnostics can contain credentials or individual row values.
            message = (
                str(error) if isinstance(error, SyncRefused) else type(error).__name__
            )
            state = load_state(STATE)
            state.update(
                last_error=message, last_attempt_at=datetime.now(UTC).isoformat()
            )
            save_state(STATE, state)
            print("Supabase sync paused: " + message, file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Execute every showcase SQL file using IDs discovered from demo data."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from api.app.db.commands import DatabaseCommandError, database_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument(
        "--showcase-dir",
        type=Path,
        default=REPOSITORY_ROOT / "db" / "showcase",
    )
    parser.add_argument("--max-rows", type=int, default=20)
    return parser


def _showcase_values(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT p.project_id, p.id AS prompt_id, pv.id AS version_id
        FROM prompts AS p
        JOIN prompt_versions AS pv ON pv.prompt_id = p.id
        ORDER BY p.created_at, pv.version_number DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("showcase queries require at least one seeded prompt version")
    return {name: str(row[name]) for name in ("project_id", "prompt_id", "version_id")}


def _render(sql: str, values: dict[str, str]) -> str:
    rendered = sql
    for name, value in values.items():
        rendered = rendered.replace(f":'{name}'", f"'{value}'")
    if ":'" in rendered:
        raise RuntimeError("showcase SQL contains an unknown variable")
    return rendered


def execute_showcase(url: str, directory: Path, max_rows: int) -> list[str]:
    if max_rows < 0:
        raise ValueError("--max-rows cannot be negative")
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise RuntimeError(f"no showcase SQL files found in {directory}")
    output: list[str] = []
    with psycopg.connect(url, row_factory=dict_row) as connection:
        values = _showcase_values(connection)
        for path in files:
            statements = [part.strip() for part in _render(path.read_text(), values).split(";") if part.strip()]
            total_rows = 0
            samples: list[dict[str, Any]] = []
            for statement in statements:
                cursor = connection.execute(statement)
                rows = cursor.fetchall() if cursor.description else []
                total_rows += len(rows)
                if len(samples) < max_rows:
                    samples.extend(rows[: max_rows - len(samples)])
            output.append(f"{path.name}: {len(statements)} statement(s), {total_rows} row(s)")
            for sample in samples:
                output.append(json.dumps(sample, default=str, sort_keys=True))
    return output


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    try:
        lines = execute_showcase(
            database_url(args.database_url), args.showcase_dir, args.max_rows
        )
    except (
        DatabaseCommandError,
        OSError,
        RuntimeError,
        ValueError,
        psycopg.Error,
    ) as exc:
        print(f"Showcase failed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export PromptVault OpenAPI JSON for frontend contract generation."""

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "web" / "dist" / "openapi.json",
    )
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()

    # Delay imports until after argument parsing so --help never requires runtime
    # settings, and until after .env loading for actual exports.
    from api.app.config import get_settings
    from api.app.main import create_app
    from api.app.openapi import export_openapi

    export_openapi(create_app(get_settings()), args.output)
    print(f"Wrote OpenAPI contract to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

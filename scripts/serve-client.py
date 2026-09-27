#!/usr/bin/env python3
"""Fetch an active PromptVault prompt through the runtime Serve API."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("PROMPTVAULT_API_URL", "http://localhost:8000"),
    )
    parser.add_argument("--token", default=os.getenv("PROMPTVAULT_SERVE_TOKEN"))
    parser.add_argument("--key", required=True, help="Prompt key")
    parser.add_argument(
        "--env",
        choices=("dev", "staging", "prod"),
        default="prod",
        help="Deployment environment",
    )
    parser.add_argument("--etag", help="Optional ETag from a previous response")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def main() -> int:
    load_dotenv(REPOSITORY_ROOT / ".env")
    args = build_parser().parse_args()
    if not args.token:
        print(
            "Serve request failed: provide --token or PROMPTVAULT_SERVE_TOKEN",
            file=sys.stderr,
        )
        return 2

    url = (
        f"{args.base_url.rstrip('/')}/serve/v1/prompts/{quote(args.key, safe='')}?"
        + urlencode({"env": args.env})
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {args.token}",
    }
    if args.etag:
        headers["If-None-Match"] = args.etag
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=args.timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 304:
            print("Prompt is unchanged (HTTP 304).")
            return 0
        print(f"Serve request failed with HTTP {exc.code}.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Serve request failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

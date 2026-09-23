"""Deterministic OpenAPI export for frontend contract generation."""

import json
from pathlib import Path

from fastapi import FastAPI


def export_openapi(application: FastAPI, output: Path) -> None:
    document = application.openapi()
    rendered = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

import json
import os
import subprocess
import sys
from pathlib import Path

from api.app.config import Settings
from api.app.main import create_app
from api.app.openapi import export_openapi

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_export_openapi_writes_deterministic_frontend_contract(
    tmp_path: Path,
    test_settings: Settings,
) -> None:
    output = tmp_path / "openapi.json"
    app = create_app(test_settings)

    export_openapi(app, output)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "PromptVault API"
    assert "/health" in document["paths"]
    assert "/ready" in document["paths"]
    assert "/api/v1/auth/register" in document["paths"]
    assert "/api/v1/auth/login" in document["paths"]
    assert "/api/v1/auth/me" in document["paths"]
    assert "ErrorEnvelope" in document["components"]["schemas"]
    register_fields = document["components"]["schemas"]["RegisterRequest"]["properties"]
    assert set(register_fields) == {"email", "password", "display_name"}
    first_render = output.read_text(encoding="utf-8")
    assert "password_hash" not in first_render
    assert "HTTPBearer" in document["components"]["securitySchemes"]
    export_openapi(app, output)
    assert output.read_text(encoding="utf-8") == first_render
    assert first_render.endswith("\n")


def test_openapi_export_script_exposes_help() -> None:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("SECRET_KEY", None)
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "export-openapi.py"), "--help"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()

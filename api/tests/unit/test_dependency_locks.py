"""Keep the CI/test environment aligned with the production runtime."""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def locked_package_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0]
        names.add(re.sub(r"[-_.]+", "-", name).lower())
    return names


def test_development_lock_contains_every_runtime_package() -> None:
    runtime = locked_package_names(REPOSITORY_ROOT / "api" / "requirements.lock")
    development = locked_package_names(
        REPOSITORY_ROOT / "api" / "requirements-dev.lock"
    )

    assert runtime <= development, (
        "requirements-dev.lock is missing runtime packages: "
        f"{sorted(runtime - development)}"
    )
